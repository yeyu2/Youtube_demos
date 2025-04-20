import React, { useEffect, useRef, useState } from "react";

interface AudioPlayerProps {
  base64Audio: string;
}

const AudioPlayer: React.FC<AudioPlayerProps> = ({ base64Audio }) => {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);

  useEffect(() => {
    if (base64Audio) {
      // Convert base64 to Blob URL
      const byteCharacters = atob(base64Audio);
      const byteNumbers = new Array(byteCharacters.length);
      for (let i = 0; i < byteCharacters.length; i++) {
        byteNumbers[i] = byteCharacters.charCodeAt(i);
      }
      const byteArray = new Uint8Array(byteNumbers);
      const blob = new Blob([byteArray], { type: "audio/pcm" }); //  Specify MIME type
      const url = URL.createObjectURL(blob);
      setAudioUrl(url);

      return () => {
        URL.revokeObjectURL(url); // Clean up the URL
      };
    }
  }, [base64Audio]);

  useEffect(() => {
    if (audioUrl && audioRef.current) {
      audioRef.current.src = audioUrl;
      audioRef.current.play().catch((error) => {
        console.error("Audio playback error:", error);
      });
    }
  }, [audioUrl]);

  return <audio ref={audioRef} controls />;
};

export default AudioPlayer;