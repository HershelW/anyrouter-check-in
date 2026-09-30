from unittest.mock import Mock

import httpx
import pytest

import checkin
from utils.config import AccountConfig, ProviderConfig


@pytest.mark.parametrize('sign_in_path', ['/api/user/sign_in', None])
def test_unauthorized_user_info_stops_account_requests(monkeypatch, capsys, sign_in_path):
	client = Mock()
	client.get.return_value = httpx.Response(401, text='not a JSON response')
	monkeypatch.setattr(
		checkin.httpx, 'Client', Mock(return_value=Mock(__enter__=Mock(return_value=client), __exit__=Mock()))
	)
	provider = ProviderConfig(name='test', domain='https://example.com', sign_in_path=sign_in_path)
	cookies = {'session': 'test-only-session'}
	account = AccountConfig(cookies=cookies, api_user='123')

	success, before, after = checkin.run_check_in_requests(cookies, account, 'Test', provider)

	assert success is False
	assert before is not None
	assert before['status_code'] == 401
	assert after is None
	client.get.assert_called_once()
	client.post.assert_not_called()
	output = capsys.readouterr().out
	assert 'ANYROUTER_ACCOUNTS' in output
	assert 'New-Api-User' in output
	assert 'test-only-session' not in output
	assert 'not a JSON response' not in output


@pytest.mark.parametrize('before_status, post_status', [(200, 200), (500, 200), (403, 200), (200, 401)])
def test_manual_checkin_response_flow(monkeypatch, capsys, before_status, post_status):
	user_info = {'success': True, 'data': {'quota': 500000, 'used_quota': 0}}
	client = Mock()
	client.get.side_effect = [httpx.Response(before_status, json=user_info), httpx.Response(200, json=user_info)]
	client.post.return_value = httpx.Response(post_status, json={'success': True})
	monkeypatch.setattr(
		checkin.httpx, 'Client', Mock(return_value=Mock(__enter__=Mock(return_value=client), __exit__=Mock()))
	)
	provider = ProviderConfig(name='test', domain='https://example.com')
	cookies = {'session': 'test-only-session'}
	account = AccountConfig(cookies=cookies, api_user='123')

	success, before, after = checkin.run_check_in_requests(cookies, account, 'Test', provider)

	client.post.assert_called_once()
	assert success is (post_status == 200)
	if post_status == 401:
		assert after is None
		assert client.get.call_count == 1
		assert 'ANYROUTER_ACCOUNTS' in capsys.readouterr().out
	else:
		assert after is not None
		assert after['success'] is True
		assert after['quota'] == 1
		assert client.get.call_count == 2
		assert 'ANYROUTER_ACCOUNTS' not in capsys.readouterr().out


@pytest.mark.asyncio
async def test_authentication_error_reaches_failure_notification(monkeypatch):
	account = AccountConfig(cookies={'session': 'test-only-session'}, api_user='123')
	client = Mock()
	client.get.return_value = httpx.Response(401)
	monkeypatch.setattr(
		checkin.httpx, 'Client', Mock(return_value=Mock(__enter__=Mock(return_value=client), __exit__=Mock()))
	)
	monkeypatch.setattr(checkin, 'load_accounts_config', lambda: [account])
	monkeypatch.setattr(checkin, 'load_balance_hash', lambda: None)
	monkeypatch.setattr(checkin, 'is_debug_enabled', lambda: False)
	monkeypatch.setenv('PROVIDERS', '{"anyrouter": {"domain": "https://example.com", "bypass_method": null}}')
	push_message = Mock()
	monkeypatch.setattr(checkin.notify, 'push_message', push_message)
	save_hash = Mock()
	monkeypatch.setattr(checkin, 'save_balance_hash', save_hash)

	with pytest.raises(SystemExit) as exc:
		await checkin.main()

	assert exc.value.code == 1
	push_message.assert_called_once()
	message = push_message.call_args.args[1]
	assert 'HTTP 401' in message
	assert 'ANYROUTER_ACCOUNTS' in message
	assert 'Success: 0/1' in message
	assert 'test-only-session' not in message
	save_hash.assert_not_called()
