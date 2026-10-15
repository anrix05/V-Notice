/**
 * V Notice - Daily Flag Event State Machine & Clock Sync Module
 * Pure logic module with injectable clock for deterministic unit testing.
 * ROTATION -> STANDUP (optional) -> FLAG -> ROTATION
 */

function computeClockOffset(serverTimeMs, requestStartMs, requestEndMs) {
  const rtt = Math.max(0, requestEndMs - requestStartMs);
  const estimatedServerNow = serverTimeMs + (rtt / 2);
  return estimatedServerNow - requestEndMs;
}

class FlagStateMachine {
  constructor(options = {}) {
    this.getNow = options.getNow || (() => Date.now());
    this.clockOffset = options.clockOffset || 0;
    this.schedule = null;
    this.state = 'ROTATION'; // 'ROTATION' | 'STANDUP' | 'FLAG'
    
    // Callbacks
    this.onEnterRotation = options.onEnterRotation || (() => {});
    this.onEnterStandup = options.onEnterStandup || (() => {});
    this.onEnterFlag = options.onEnterFlag || (() => {});
    this.onExitFlag = options.onExitFlag || (() => {});
    this.onStateChange = options.onStateChange || (() => {});
  }

  updateClockOffset(serverTimeMs, requestStartMs, requestEndMs) {
    this.clockOffset = computeClockOffset(serverTimeMs, requestStartMs, requestEndMs);
    return this.clockOffset;
  }

  getCurrentServerTime() {
    return this.getNow() + this.clockOffset;
  }

  setSchedule(schedule) {
    this.schedule = schedule;
    this.evaluate();
  }

  getSchedule() {
    return this.schedule;
  }

  getState() {
    return this.state;
  }

  evaluate() {
    const previousState = this.state;
    const now = this.getCurrentServerTime();

    if (!this.schedule || !this.schedule.flag_start_ms || !this.schedule.flag_end_ms) {
      if (this.state !== 'ROTATION') {
        const wasFlag = this.state === 'FLAG';
        this.state = 'ROTATION';
        if (wasFlag) this.onExitFlag();
        this.onEnterRotation();
        this.onStateChange(this.state, previousState);
      }
      return this.state;
    }

    const startMs = this.schedule.flag_start_ms;
    const endMs = this.schedule.flag_end_ms;
    const showStandup = Boolean(this.schedule.show_standup_text);
    const leadSec = showStandup ? (this.schedule.standup_lead_seconds || 15) : 0;
    const standupStartMs = startMs - (leadSec * 1000);

    let nextState = 'ROTATION';
    if (now >= startMs && now < endMs) {
      nextState = 'FLAG';
    } else if (leadSec > 0 && now >= standupStartMs && now < startMs) {
      nextState = 'STANDUP';
    } else {
      nextState = 'ROTATION';
    }

    if (nextState !== this.state) {
      const oldState = this.state;
      this.state = nextState;

      if (oldState === 'FLAG' && nextState !== 'FLAG') {
        this.onExitFlag();
      }

      if (nextState === 'ROTATION') {
        this.onEnterRotation();
      } else if (nextState === 'STANDUP') {
        const remainingLeadMs = Math.max(0, startMs - now);
        this.onEnterStandup({ remainingLeadMs });
      } else if (nextState === 'FLAG') {
        const remainingDurationMs = Math.max(0, endMs - now);
        this.onEnterFlag({ remainingDurationMs });
      }

      this.onStateChange(nextState, oldState);
    }

    return this.state;
  }
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { FlagStateMachine, computeClockOffset };
}
if (typeof window !== 'undefined') {
  window.FlagStateMachine = FlagStateMachine;
  window.computeClockOffset = computeClockOffset;
}
