import { HashRouter, Routes, Route, useLocation } from "react-router-dom";
import { useEffect, useState } from "react";

import HomePage from "./pages/HomePage";
import DropPage from "./pages/DropPage";
import ModeSelect from "./pages/ModeSelect";
import DetectorHUD from "./components/DetectorHUD";
import { useDuskDetector } from "./detect/useDuskDetector";
import { logEvent, startMetricsFlusher } from "./metrics";
import { FORCED_MODE, TAU } from "./config";

const HEARTBEAT_MS = 60000;   // battery sample cadence for drain curves

const App = () => {
  const [mode, setMode] = useState(FORCED_MODE);   // "always" | "dusk" | null

  useEffect(() => startMetricsFlusher(), []);

  // battery time series: one sample per minute while a mode is active —
  // this is the raw data for the thesis battery-drain A/B curves
  useEffect(() => {
    if (!mode) return;
    logEvent("session_start", { mode });
    logEvent("battery_sample", { mode });
    const t = setInterval(() => logEvent("battery_sample", { mode }), HEARTBEAT_MS);
    return () => clearInterval(t);
  }, [mode]);

  if (!mode) return <ModeSelect onSelect={setMode} />;
  return (
    <HashRouter>
      <Detecting mode={mode} />
    </HashRouter>
  );
};

const Detecting = ({ mode }) => {
  const [gesture, setGesture] = useState({ label: null, conf: 0, at: 0 });
  const location = useLocation();

  // each page only listens for its own gesture
  const allowed = location.pathname === "/drop" ? ["drop"] : ["grab"];

  const { status, modelReady, cameraOn, lastCommit, tier1, videoRef } = useDuskDetector({
    mode,
    tau: TAU,
    allowed,
    onGesture: (label, conf) => setGesture({ label, conf, at: Date.now() }),
  });

  return (
    <>
      <DetectorHUD mode={mode} status={status} modelReady={modelReady}
                   cameraOn={cameraOn} lastCommit={lastCommit} tier1={tier1}
                   videoRef={videoRef} />
      <Routes>
        <Route path="/" element={
          <HomePage currentGesture={gesture.label}
                    gestureConfidence={gesture.conf} gestureAt={gesture.at} />
        } />
        <Route path="/drop" element={
          <DropPage currentGesture={gesture.label}
                    gestureConfidence={gesture.conf} gestureAt={gesture.at} />
        } />
      </Routes>
    </>
  );
};

export default App;
