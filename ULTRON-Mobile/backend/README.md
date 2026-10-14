# ULTRON Protected AI Gateway

Este serviço mantém a chave Groq exclusivamente no servidor. O APK nunca deve conter a chave Groq.

## Executar localmente

Requer Python 3.11+.

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
# Configure GROQ_API_KEY no ambiente do processo; não comite um arquivo .env real.
uvicorn app.main:app --host 127.0.0.1 --port 8080
```

Configure `GROQ_API_KEY` como secret/environment variable no serviço de hospedagem. Use HTTPS em produção. Não exponha o servidor de desenvolvimento diretamente à internet. O limite por IP em memória é uma proteção básica; em produção com múltiplas instâncias, configure rate limiting no gateway/provedor e monitore custos.

## Contrato

- `GET /health`: status mínimo e indicação booleana se o segredo está configurado; não revela a chave.
- `POST /v1/chat`: JSON com `message` e até 12 mensagens de histórico (`role`: `user` ou `assistant`). Retorna `reply` e `model`.
- Mensagem: até 4.000 caracteres; timeout upstream; erros upstream não são repassados em bruto.

## Testes

```bash
pip install -r requirements.txt
pytest -q
```

Este PR fornece o serviço e o adaptador Android. A IA online só funcionará depois que o backend for implantado com a secret e a URL HTTPS configuradas no build do aplicativo.