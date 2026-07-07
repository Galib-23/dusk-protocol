// Tier 1 — wave triggers (PROJECT_REFERENCE §architecture). Rule-based,
// no ML. Two detectors, either can fire:
//   WaveDetector     — IR proximity near/far cycles (range ~0-5 cm)
//   LightDipDetector — ambient-light shadow dips: a hand waved 7-15 cm
//                      above the phone dims the lux reading. Needs some
//                      ambient light; proximity remains the dark fallback.

export class WaveDetector {
  constructor({ cycles = 3, windowMs = 2000 } = {}) {
    this.cycles = cycles;
    this.windowMs = windowMs;
    this.onsets = [];
    this.wasNear = false;
  }

  reset() {
    this.onsets = [];
    this.wasNear = false;
  }

  // feed a proximity event; returns true exactly when the wave fires
  update(near, now = Date.now()) {
    const onset = near && !this.wasNear;
    this.wasNear = near;
    if (!onset) return false;
    this.onsets.push(now);
    this.onsets = this.onsets.filter((t) => now - t <= this.windowMs);
    if (this.onsets.length >= this.cycles) {
      this.reset();
      return true;
    }
    return false;
  }
}

export class LightDipDetector {
  constructor({ dips = 2, windowMs = 3000, dipRatio = 0.78,
                recoverRatio = 0.9, minLux = 10 } = {}) {
    this.dips = dips;
    this.windowMs = windowMs;
    this.dipRatio = dipRatio;
    this.recoverRatio = recoverRatio;
    this.minLux = minLux;
    this.reset();
  }

  reset() {
    this.baseline = null;
    this.inDip = false;
    this.onsets = [];
  }

  // feed a lux reading; returns true exactly when the wave fires
  update(lux, now = Date.now()) {
    if (this.baseline === null) {
      this.baseline = lux;
      return false;
    }
    // track ambient level only while not shadowed, slowly (EMA)
    if (!this.inDip) this.baseline = 0.95 * this.baseline + 0.05 * lux;
    if (this.baseline < this.minLux) return false;   // too dark to be reliable

    if (!this.inDip && lux < this.dipRatio * this.baseline) {
      this.inDip = true;
      this.onsets.push(now);
      this.onsets = this.onsets.filter((t) => now - t <= this.windowMs);
      if (this.onsets.length >= this.dips) {
        this.onsets = [];
        this.inDip = false;
        return true;
      }
    } else if (this.inDip && lux > this.recoverRatio * this.baseline) {
      this.inDip = false;
    }
    return false;
  }
}
