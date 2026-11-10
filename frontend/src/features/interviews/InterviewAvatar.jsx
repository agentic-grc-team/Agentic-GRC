import { useEffect, useState } from "react";
import "./InterviewAvatar.css";

export default function InterviewAvatar({ state }) {
  const [imageFailed, setImageFailed] = useState(false);
  const [blinking, setBlinking] = useState(false);
  const [blinkReady, setBlinkReady] = useState(false);
  const [mouthReady, setMouthReady] = useState(false);
  const [smileReady, setSmileReady] = useState(false);

  useEffect(() => {
    if (!blinkReady || imageFailed) return;

    const motion = window.matchMedia?.("(prefers-reduced-motion: reduce)") || { matches: false };
    let timer;
    let disposed = false;

    function scheduleBlink() {
      timer = window.setTimeout(() => {
        if (disposed) return;

        if (document.hidden || motion.matches) {
          scheduleBlink();
          return;
        }

        setBlinking(true);

        timer = window.setTimeout(() => {
          if (disposed) return;
          setBlinking(false);
          scheduleBlink();
        }, 140);
      }, 3500 + Math.random() * 2500);
    }

    scheduleBlink();

    return () => {
      disposed = true;
      window.clearTimeout(timer);
    };
  }, [blinkReady, imageFailed]);

  const attentive = state === "typing" || state === "processing";
  if (imageFailed) return null;

  return (
    <div className={`interview-avatar-figure interview-avatar-${state}`} aria-hidden="true">
      <div className="interview-avatar-halo" />

      <div className="interview-avatar-portrait">
        <img
          className="interview-avatar-base interview-avatar-body"
          onError={() => setImageFailed(true)}
          src="/avatars/interview-guide.png"
          alt=""
          draggable="false"
        />

        <div className="interview-avatar-head-motion">
          <img
            className="interview-avatar-base"
            src="/avatars/interview-guide.png"
            alt=""
            draggable="false"
          />
          <img
            className={`interview-avatar-face-layer interview-avatar-mouth ${smileReady ? "is-visible" : ""}`}
            src="/avatars/interview-guide-smile.png"
            alt=""
            draggable="false"
            onLoad={() => setSmileReady(true)}
            onError={() => setSmileReady(false)}
          />
          <img
            className={`interview-avatar-face-layer interview-avatar-mouth ${
              attentive && mouthReady ? "is-visible" : ""
            }`}
            src="/avatars/interview-guide-attentive.png"
            alt=""
            draggable="false"
            onLoad={() => setMouthReady(true)}
            onError={() => setMouthReady(false)}
          />

          <img
            className={`interview-avatar-face-layer interview-avatar-blink ${
              blinking && blinkReady ? "is-visible" : ""
            }`}
            src="/avatars/interview-guide-blink.png"
            alt=""
            draggable="false"
            onLoad={() => setBlinkReady(true)}
            onError={() => setBlinkReady(false)}
          />
        </div>
      </div>
    </div>
  );
}

