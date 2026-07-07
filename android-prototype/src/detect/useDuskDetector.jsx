// The whole Tier-1 + Tier-2 pipeline as one React hook.
//
//   mode "always": camera runs continuously, gesture windows back-to-back
//   mode "dusk"  : camera OFF; a proximity/light wave (Tier 1) wakes it;
//                  after a commit or SESSION_MS timeout it sleeps again
//
// `allowed` scopes which gestures may commit (the grab page only accepts
// "grab", the drop page only "drop"); other detections are logged as
// ignored and the window keeps watching.
//
// Camera "off" is real: the MediaStream tracks are stopped, which powers
// down the sensor. Every transition is logged via metrics.js.

import { useEffect, useRef, useState } from "react";
import { FilesetResolver, HandLandmarker } from "@mediapipe/tasks-vision";

import { FeatureStream } from "../model/features";
import { loadModel, NONE } from "../model/gru";
import { watchWakeTrigger } from "./proximity";
import { logEvent } from "../metrics";

const FEED_MS = 66;        // ~15 fps into the GRU (training rate)
const SESSION_MS = 10000;  // dusk: give up and sleep if no gesture by then
const COMMIT_HOLD_MS = 1500;

export function useDuskDetector({ mode, tau = 0.9, allowed, onGesture }) {
  const [status, setStatus] = useState("loading");   // loading|sleeping|watching|committed
  const [modelReady, setModelReady] = useState(false);
  const [cameraOn, setCameraOn] = useState(false);
  const [lastCommit, setLastCommit] = useState(null);
  const [tier1, setTier1] = useState(null);           // {lux, baseline, near}
  const videoRef = useRef(null);
  const lastTier1Update = useRef(0);

  const ref = useRef({});
  ref.current.onGesture = onGesture;
  ref.current.tau = tau;
  ref.current.mode = mode;
  ref.current.allowed = allowed;

  useEffect(() => {
    let alive = true;
    const S = {
      landmarker: null, gru: null, stream: null, raf: 0,
      feats: new FeatureStream(), lastFeed: 0, lastVideoTs: -1,
      sessionStart: 0, camOnAt: 0, unwatch: null,
    };

    const camOff = async (reason) => {
      cancelAnimationFrame(S.raf);
      if (S.stream) {
        S.stream.getTracks().forEach((t) => t.stop());
        S.stream = null;
        setCameraOn(false);
        await logEvent("camera_off", {
          mode: ref.current.mode, reason,
          camera_on_ms: Date.now() - S.camOnAt,
        });
      }
      S.gru?.reset();
      S.feats.reset();
    };

    const loop = () => {
      if (!alive || !S.stream) return;
      S.raf = requestAnimationFrame(loop);
      const video = videoRef.current;
      const now = performance.now();
      if (!video || video.readyState < 2) return;
      if (now - S.lastFeed < FEED_MS) return;
      if (video.currentTime === S.lastVideoTs) return;
      S.lastFeed = now;
      S.lastVideoTs = video.currentTime;

      const res = S.landmarker.detectForVideo(video, now);
      const lm = res.landmarks?.[0];
      if (!lm) {
        S.gru.reset();
        S.feats.reset();
      } else {
        const pts = lm.map((p) => ({ x: p.x * video.videoWidth,
                                     y: p.y * video.videoHeight }));
        const out = S.gru.step(S.feats.next(pts));
        if (out) {
          const fire = out.cls !== NONE && out.conf >= ref.current.tau;
          if (fire) {
            S.gru.reset();
            S.feats.reset();
            const ok = !ref.current.allowed ||
                       ref.current.allowed.includes(out.label);
            if (ok) {
              commit(out);
              return;
            }
            // wrong gesture for this page — note it, keep watching
            logEvent("commit_ignored", {
              mode: ref.current.mode, label: out.label,
              conf: out.conf, frames: out.frame,
            });
          } else if (out.frame >= S.gru.maxFrames) {
            S.gru.reset();
            S.feats.reset();
          }
        }
      }
      if (ref.current.mode === "dusk" &&
          Date.now() - S.sessionStart > SESSION_MS) {
        camOff("timeout");
        logEvent("timeout", { mode: "dusk" });
        setStatus("sleeping");
      }
    };

    const commit = async (out) => {
      const info = { label: out.label, conf: out.conf, frames: out.frame,
                     wake_to_commit_ms: Date.now() - S.sessionStart };
      await logEvent("commit", { mode: ref.current.mode, ...info });
      setLastCommit(info);
      ref.current.onGesture?.(out.label, out.conf, info);
      if (ref.current.mode === "dusk") {
        await camOff("early_exit");
        setStatus("committed");
        setTimeout(() => alive && setStatus("sleeping"), COMMIT_HOLD_MS);
      } else {
        setStatus("committed");
        setTimeout(() => alive && setStatus("watching"), COMMIT_HOLD_MS);
      }
    };

    const camOn = async () => {
      if (S.stream || !alive) return;
      S.sessionStart = Date.now();
      S.camOnAt = Date.now();
      S.stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: 640, height: 480 },
      });
      const video = videoRef.current;
      video.srcObject = S.stream;
      await video.play();
      setCameraOn(true);
      await logEvent("camera_on", { mode: ref.current.mode });
      setStatus("watching");
      S.lastFeed = 0;
      loop();
    };

    (async () => {
      const fileset = await FilesetResolver.forVisionTasks("/wasm");
      S.landmarker = await HandLandmarker.createFromOptions(fileset, {
        baseOptions: { modelAssetPath: "/model/hand_landmarker.task",
                       delegate: "GPU" },
        runningMode: "VIDEO",
        numHands: 1,
      });
      S.gru = await loadModel();
      if (!alive) return;
      setModelReady(true);

      if (mode === "always") {
        await camOn();
      } else {
        setStatus("sleeping");
        S.unwatch = await watchWakeTrigger(
          async (source) => {
            if (!alive || S.stream) return;
            await logEvent("wake", { mode: "dusk", source });
            await camOn();
          },
          (reading) => {   // throttled sensor readout for the debug HUD
            const now = Date.now();
            if (now - lastTier1Update.current < 400) return;
            lastTier1Update.current = now;
            alive && setTier1((prev) => ({ ...prev, ...reading }));
          });
      }
    })().catch((e) => {
      console.error("detector init failed", e);
      alive && setStatus("error: " + e.message);
    });

    return () => {
      alive = false;
      camOff("unmount");
      S.unwatch?.();
    };
  }, [mode]);

  return { status, modelReady, cameraOn, lastCommit, tier1, videoRef };
}
