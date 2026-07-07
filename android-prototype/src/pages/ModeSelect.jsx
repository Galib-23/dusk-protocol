import { Camera, MoonStar } from "lucide-react";

const ModeSelect = ({ onSelect }) => (
  <div className="min-h-screen bg-gray-950 text-white flex flex-col items-center justify-center gap-6 p-6">
    <h1 className="text-3xl font-bold">🌒 Dusk Protocol</h1>
    <p className="text-gray-400 text-center text-sm max-w-xs">
      Pick the experiment arm for this session. Both run the same early-exit
      gesture model — only the camera policy differs.
    </p>

    <button onClick={() => onSelect("always")}
            className="w-full max-w-xs bg-red-600/90 hover:bg-red-600 rounded-2xl p-6 text-left">
      <Camera className="w-8 h-8 mb-2" />
      <div className="text-xl font-semibold">Always-On (baseline)</div>
      <div className="text-sm text-red-100">Camera streams continuously</div>
    </button>

    <button onClick={() => onSelect("dusk")}
            className="w-full max-w-xs bg-indigo-600/90 hover:bg-indigo-600 rounded-2xl p-6 text-left">
      <MoonStar className="w-8 h-8 mb-2" />
      <div className="text-xl font-semibold">Dusk (proximity-gated)</div>
      <div className="text-sm text-indigo-100">
        Camera sleeps — wave over the proximity sensor to wake it
      </div>
    </button>
  </div>
);

export default ModeSelect;
