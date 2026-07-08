// Tier-1 wake trigger: combines the native Proximity plugin's two streams —
// IR near/far events (0-5 cm) and ambient-light lux readings (hand shadow
// from 7-15+ cm) — and fires onWake once when either wave detector trips.
//
// Web fallback (npm run dev): press P to simulate a wave.

import { Capacitor, registerPlugin } from "@capacitor/core";
import { WaveDetector, LightDipDetector } from "./waveDetector";

const Proximity = registerPlugin("Proximity");

// onWake(source); onReading({lux, baseline, near}) for the debug HUD.
// Returns an async unsubscribe function.
export async function watchWakeTrigger(onWake, onReading) {
  if (Capacitor.isNativePlatform()) {
    const prox = new WaveDetector();
    const dips = new LightDipDetector();

    const subProx = await Proximity.addListener("proximity", ({ near }) => {
      if (prox.update(near)) onWake("proximity");
      onReading?.({ near });
    });
    const subLight = await Proximity.addListener("light", ({ lux }) => {
      if (dips.update(lux)) onWake("light");
      onReading?.({ lux, baseline: dips.baseline });
    });
    const caps = await Proximity.start();
    console.log("[tier1] sensors:", JSON.stringify(caps));

    return async () => {
      await subProx.remove();
      await subLight.remove();
      await Proximity.stop();
    };
  }

  const onKey = (e) => {
    if (e.key.toLowerCase() === "p") onWake("keyboard");
  };
  window.addEventListener("keydown", onKey);
  return () => window.removeEventListener("keydown", onKey);
}
