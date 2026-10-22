export class RealTransport {
  constructor({ bridge = window.ultron, onEvent = () => {} }) {
    this.bridge = bridge;
    this.onEvent = onEvent;
    this.mode = 'real';
    this.timer = null;
    this.polling = false;
    this.online = false;
  }

  async connect({ poll = true } = {}) {
    if (!this.bridge) throw new Error('A ponte segura do ULTRON não está disponível.');
    if (poll) this.timer = setInterval(() => this.poll(), 750);
    try {
      await this.bridge.health();
      this.online = true;
      this.onEvent({ event: 'ULTRON_ONLINE', data: {} });
      await this.poll();
    } catch (error) {
      this.online = false;
      this.onEvent({ event: 'ULTRON_OFFLINE', data: {} });
      throw error;
    }
  }

  async poll() {
    if (this.polling) return;
    this.polling = true;
    try {
      const [status, result] = await Promise.all([this.bridge.status(), this.bridge.events()]);
      if (!this.online) this.onEvent({ event: 'ULTRON_ONLINE', data: {} });
      this.online = true;
      this.onEvent({ event: 'SYSTEM_STATUS', data: status });
      for (const event of result.events || []) {
        if (event.type === 'command_result') {
          this.onEvent({ event: 'COMMAND_RESULT', request_id: event.operation_id,
            data: { response: event.response } });
        } else if (event.type === 'notification') {
          this.onEvent({ event: 'NOTIFICATION', data: { message: event.message } });
        } else if (event.type === 'conversation_turn') {
          // bat-papo de voz: fala reconhecida ou resposta do núcleo
          this.onEvent({ event: 'CONVERSATION_TURN', data: { role: event.role, text: event.text,
            source: event.source, at: event.at } });
        } else if (event.type === 'confirmation_request') {
          this.onEvent({ event: 'CONFIRMATION_REQUIRED', request_id: event.request_id,
            data: { message: event.message, risk: event.risk, requires_pin: event.requires_pin } });
        }
      }
    } catch {
      if (this.online) this.onEvent({ event: 'ULTRON_OFFLINE', data: {} });
      this.online = false;
    } finally {
      this.polling = false;
    }
  }

  command(text) { return this.bridge.command(text); }
  setMicrophonePaused(paused) { return this.bridge.microphone(paused); }
  listMicrophones() { return this.bridge.microphones(); }
  conversation() { return this.bridge.conversation(); }
  selectMicrophone(deviceId) { return this.bridge.selectMicrophone(deviceId); }
  confirm(requestId, approved, pin) { return this.bridge.confirmation(requestId, approved, pin); }
  emergencyStop() { return this.bridge.emergencyStop(); }
  shutdown() { return this.bridge.shutdown(); }

  disconnect() {
    clearInterval(this.timer);
    this.timer = null;
  }
}
