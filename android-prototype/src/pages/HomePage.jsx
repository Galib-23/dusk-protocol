import { useEffect, useRef, useState } from "react";
import { Upload } from "lucide-react";
import { Link } from "react-router-dom";
import { API_URL, USER_ID, GRAB_COOLDOWN, CONFIDENCE_THRESHOLD } from "../config";

const HomePage = ({ currentGesture, gestureConfidence, gestureAt }) => {
  const [selectedImage, setSelectedImage] = useState(null);
  const [imagePreview, setImagePreview] = useState(null);
  const [isGrabbing, setIsGrabbing] = useState(false);
  const [hasGrabbed, setHasGrabbed] = useState(false);

  const lastGrabTime = useRef(0);

  const handleGrab = async () => {
    if (!selectedImage || isGrabbing) return;
    lastGrabTime.current = Date.now();
    setIsGrabbing(true);

    const formData = new FormData();
    formData.append("image", selectedImage);
    formData.append("userId", USER_ID);

    try {
      const response = await fetch(`${API_URL}/upload`, {
        method: "POST",
        body: formData,
      });
      const data = await response.json();
      if (data.success) {
        setHasGrabbed(true);
        setTimeout(() => setIsGrabbing(false), 2000);
      } else {
        setIsGrabbing(false);
      }
    } catch (error) {
      console.error(error);
      setIsGrabbing(false);
      setHasGrabbed(false);
    }
  };

  // fires once per committed gesture event (gestureAt = commit timestamp)
  useEffect(() => {
    if (
      currentGesture === "grab" &&
      gestureConfidence > CONFIDENCE_THRESHOLD &&
      selectedImage &&
      !isGrabbing &&
      !hasGrabbed &&
      Date.now() - lastGrabTime.current > GRAB_COOLDOWN
    ) {
      handleGrab();
    }
  }, [gestureAt]);

  const handleImageSelect = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setSelectedImage(file);
    setHasGrabbed(false);
    lastGrabTime.current = 0;
    const reader = new FileReader();
    reader.onloadend = () => setImagePreview(reader.result);
    reader.readAsDataURL(file);
  };

  return (
    <div className="min-h-screen bg-linear-to-br from-blue-50 to-indigo-100 flex flex-col items-center justify-center p-4 pt-12">
      {!imagePreview ? (
        <div className="bg-white rounded-2xl shadow-2xl p-8 max-w-md w-full">
          <h1 className="text-3xl font-bold text-gray-800 mb-6 text-center">
            Image Transfer
          </h1>
          <p className="text-gray-600 mb-6 text-center">
            Select an image, then make a <strong>"GRAB"</strong> gesture
            (close your open hand into a fist)
          </p>

          <label className="flex flex-col items-center justify-center w-full h-64 border-2 border-dashed border-indigo-300 rounded-xl cursor-pointer hover:border-indigo-500 transition-colors bg-indigo-50 hover:bg-indigo-100">
            <Upload className="w-16 h-16 text-indigo-400 mb-4" />
            <span className="text-sm text-gray-600">Tap to select image</span>
            <input type="file" className="hidden" accept="image/*"
                   onChange={handleImageSelect} />
          </label>

          <Link to="/drop"
                className="mt-6 w-fit flex items-center justify-center gap-2 text-gray-600 underline py-2 text-xs rounded-xl transition-colors">
            Go to Drop Page
          </Link>
        </div>
      ) : (
        <div className="relative w-full h-screen">
          <img src={imagePreview} alt="Selected"
               className="w-full h-full object-contain" />
          {hasGrabbed && !isGrabbing && (
            <div className="absolute bottom-8 inset-x-0 text-center text-emerald-600 font-semibold">
              Grabbed! Open the Drop page on the other phone.
            </div>
          )}
          {isGrabbing && (
            <div className="absolute inset-0 flex items-center justify-center bg-black bg-opacity-50">
              <div className="animate-ping absolute w-96 h-96 rounded-full bg-white opacity-75"></div>
              <div className="animate-pulse absolute w-64 h-64 rounded-full bg-white opacity-75"></div>
              <div className="animate-bounce absolute w-32 h-32 rounded-full bg-white opacity-75"></div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default HomePage;
