import json

import pytest

from utils.config import AppConfig, ProviderConfig


def test_builtin_provider_profile_persistence_defaults(monkeypatch):
	monkeypatch.delenv('PROVIDERS', raising=False)

	config = AppConfig.load_from_env()

	assert config.providers['anyrouter'].persist_profile is True
	assert config.providers['agentrouter'].persist_profile is False


def test_provider_profile_persistence_can_override_builtin(monkeypatch):
	monkeypatch.setenv(
		'PROVIDERS',
		json.dumps(
			{
				'anyrouter': {'domain': 'https://anyrouter.top', 'persist_profile': False},
				'agentrouter': {'domain': 'https://agentrouter.org', 'persist_profile': True},
			}
		),
	)

	config = AppConfig.load_from_env()

	assert config.providers['anyrouter'].persist_profile is False
	assert config.providers['agentrouter'].persist_profile is True


def test_custom_provider_profile_persistence_defaults_to_false(monkeypatch):
	monkeypatch.setenv('PROVIDERS', json.dumps({'custom': {'domain': 'https://custom.example.com'}}))

	config = AppConfig.load_from_env()

	assert config.providers['custom'].persist_profile is False


def test_provider_from_dict_inherits_profile_persistence_from_defaults():
	defaults = ProviderConfig(name='custom', domain='https://old.example.com', persist_profile=True)

	provider = ProviderConfig.from_dict(
		'custom',
		{'domain': 'https://new.example.com'},
		defaults=defaults,
	)

	assert provider.persist_profile is True


@pytest.mark.parametrize('name', ['anyrouter', 'agentrouter'])
def test_builtin_provider_partial_override_inherits_defaults(monkeypatch, capsys, name):
	monkeypatch.delenv('PROVIDERS', raising=False)
	defaults = AppConfig.load_from_env().providers[name]
	monkeypatch.setenv('PROVIDERS', json.dumps({name: {'use_proxy': not defaults.use_proxy}}))

	provider = AppConfig.load_from_env().providers[name]

	assert provider.domain == defaults.domain
	assert provider.use_proxy is not defaults.use_proxy
	assert provider.sign_in_path == defaults.sign_in_path
	assert provider.waf_cookie_names == defaults.waf_cookie_names
	assert provider.bypass_method == defaults.bypass_method
	assert provider.persist_profile == defaults.persist_profile
	assert 'Loaded 1 custom provider(s)' in capsys.readouterr().out


@pytest.mark.parametrize('domain', [None, '', 123, 'example.com', 'ftp://example.com', 'https://', 'https://bad host'])
def test_invalid_provider_domains_are_skipped(monkeypatch, capsys, domain):
	monkeypatch.setenv(
		'PROVIDERS',
		json.dumps({'anyrouter': {'domain': domain}, 'custom': {'domain': domain}, 'missing': {}}),
	)

	config = AppConfig.load_from_env()

	assert config.providers['anyrouter'].domain == 'https://anyrouter.top'
	assert 'custom' not in config.providers
	assert 'missing' not in config.providers
	assert 'Loaded 0 custom provider(s)' in capsys.readouterr().out


def test_only_successfully_loaded_providers_are_counted(monkeypatch, capsys):
	monkeypatch.setenv('PROVIDERS', json.dumps({'custom': {'domain': 'https://example.com'}, 'missing': {}}))

	config = AppConfig.load_from_env()

	assert config.providers['custom'].domain == 'https://example.com'
	assert 'missing' not in config.providers
	assert 'Loaded 1 custom provider(s)' in capsys.readouterr().out
