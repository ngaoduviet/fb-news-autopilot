from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_no_openai_runtime_dependency():
    forbidden = ('OPENAI_API_KEY', 'OPENAI_DISCOVERY_MODEL', 'OPENAI_SEMANTIC_MODEL',
                 'import openai', 'from openai', 'OpenAI(', 'responses.create')
    source = '\n'.join(path.read_text(encoding='utf-8') for path in (ROOT / 'src').rglob('*.py'))
    configuration = (ROOT / 'pyproject.toml').read_text(encoding='utf-8') + (ROOT / '.env.example').read_text(encoding='utf-8')
    for marker in forbidden:
        assert marker not in source
    assert '"openai' not in configuration.casefold()
    assert 'OPENAI_' not in configuration
