# ULTRON Web Mock Protocol v1

## Envelope

Eventos usam:

```json
{
  "protocol_version": "1.0",
  "event": "EVENT_NAME",
  "timestamp": "ISO-8601",
  "request_id": "uuid-or-null",
  "session_id": "uuid-or-null",
  "data": {}
}
```

## Connection events

`ULTRON_ONLINE`, `ULTRON_OFFLINE`, `SESSION_EXPIRED`

## Command events

`COMMAND_STARTED`, `COMMAND_COMPLETED`, `COMMAND_FAILED`

## Confirmation

`CONFIRMATION_REQUIRED`

Data:

```json
{
  "action": "Desligar o computador",
  "risk": "ALTO",
  "expires_at": "ISO-8601",
  "original_command": "Desligue o computador"
}
```

## Voice

`VOICE_LISTENING`, `VOICE_TRANSCRIPT`, `VOICE_RESPONSE`

## System

`SYSTEM_STATUS`

```json
{
  "cpu": {"usage": 24},
  "memory": {"usage": 48},
  "gpu": {"usage": 31},
  "temperature": {"cpu": 52},
  "storage": {"usage": 67},
  "network": {"online": true}
}
```

## Tasks

`TASK_CREATED`, `TASK_COMPLETED` — reservados para fases futuras.

## Visual state mapping

| Protocol event | Visual state |
|---|---|
| ULTRON_ONLINE | IDLE |
| ULTRON_OFFLINE | OFFLINE |
| VOICE_LISTENING | LISTENING |
| COMMAND_STARTED | THINKING |
| VOICE_RESPONSE | SPEAKING |
| CONFIRMATION_REQUIRED | CONFIRMING |
| COMMAND_COMPLETED | SUCCESS |
| COMMAND_FAILED | ERROR |
| SESSION_EXPIRED | OFFLINE |

## Commands

HTTP real:

- `GET /api/v1/health`
- `GET /api/v1/status`
- `POST /api/v1/command`
- `POST /api/v1/confirmation`

O Mock reproduz semanticamente essas operações no browser.

## Security invariants

1. O frontend não executa shell.
2. O frontend não acessa o Windows diretamente.
3. O frontend não decide ALLOW/CONFIRM/DENY.
4. O frontend não recebe PIN ou segredo interno.
5. Confirmação sempre usa `request_id` + `session_id` e expiração.
6. O modo real deve usar HTTPS/WSS.
