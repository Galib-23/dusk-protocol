// Floating status pill (top-right): model + camera state at a glance on
// every page, plus the last committed gesture with frames-to-decision.

import { BrainCircuit, Camera, CameraOff, MoonStar } from "lucide-react";

const Dot = ({ on, pulse }) => (
  <span className={`w-2 h-2 rounded-full shrink-0
    ${on ? "bg-emerald-400" : "bg-gray-500"} ${pulse ? "animate-pulse" : ""}`} />
);

const DetectorHUD = ({ mode, status, modelReady, cameraOn, lastCommit, tier1, videoRef }) => {
  const sleeping = status === "sleeping";
  return (
    <>
      <div className="fixed top-3 right-3 z-50 select-none">
        <div className="flex items-center gap-3 bg-gray-900/90 backdrop-blur text-white
                        rounded-full px-4 py-2 shadow-lg text-xs font-medium">
          <span className="flex items-center gap-1.5" title="gesture model">
            <BrainCircuit className={`w-4 h-4 ${modelReady ? "text-emerald-400" : "text-gray-500"}`} />
            <Dot on={modelReady} pulse={!modelReady} />
          </span>

          <span className="flex items-center gap-1.5" title="camera">
            {cameraOn
              ? <Camera className="w-4 h-4 text-emerald-400" />
              : <CameraOff className="w-4 h-4 text-gray-400" />}
            <Dot on={cameraOn} pulse={cameraOn} />
          </span>

          <span className={`uppercase tracking-wide text-[10px] px-2 py-0.5 rounded-full
            ${mode === "dusk" ? "bg-indigo-500/60" : "bg-red-500/60"}`}>
            {mode === "dusk" ? <MoonStar className="w-3 h-3 inline mr-1 -mt-px" /> : null}
            {mode}
          </span>
        </div>

        {sleeping && (
          <div className="mt-1.5 text-right">
            <span className="inline-block bg-indigo-600/90 text-white text-[10px]
                             rounded-full px-3 py-1 shadow">
              wave over the top of the phone to wake
              {tier1?.lux !== undefined &&
                ` · lux ${Math.round(tier1.lux)}/${Math.round(tier1.baseline ?? 0)}`}
              {tier1?.near !== undefined && (tier1.near ? " · NEAR" : "")}
            </span>
          </div>
        )}
        {lastCommit && (
          <div className="mt-1.5 text-right">
            <span className="inline-block bg-gray-900/80 text-emerald-300 font-mono
                             text-[10px] rounded-full px-3 py-1 shadow">
              {lastCommit.label} @ {lastCommit.frames} frames ({lastCommit.conf.toFixed(2)})
            </span>
          </div>
        )}
      </div>

      {/* hidden video element the detector feeds from */}
      <video ref={videoRef} autoPlay muted playsInline
             className="fixed w-px h-px opacity-0 pointer-events-none" />
    </>
  );
};

export default DetectorHUD;
