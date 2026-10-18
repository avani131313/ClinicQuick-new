"use client";

import { useEffect, useRef, useState } from "react";

/** Browser speech-to-text (Chrome, Edge, Safari). Firefox has no support, so `supported` is false there. */
export function useSpeechInput(onText: (text: string, final: boolean) => void) {
  const recRef = useRef<any>(null);
  const [supported, setSupported] = useState(false);
  const [listening, setListening] = useState(false);
  const [error, setError] = useState("");
  const cb = useRef(onText);
  cb.current = onText;

  useEffect(() => {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) return;
    setSupported(true);
    const rec = new SR();
    rec.lang = "en-CA";
    rec.interimResults = true;
    rec.continuous = false;
    rec.onresult = (e: any) => {
      let text = "", final = false;
      for (let i = 0; i < e.results.length; i++) {
        text += e.results[i][0].transcript;
        if (e.results[i].isFinal) final = true;
      }
      cb.current(text.trim(), final);
    };
    rec.onerror = (e: any) => {
      setError(e.error === "not-allowed" ? "Microphone access is blocked. Allow it in your browser's site settings." : e.error === "no-speech" ? "Didn't catch that. Try again." : "Voice input stopped. You can type instead.");
      setListening(false);
    };
    rec.onend = () => setListening(false);
    recRef.current = rec;
    return () => { try { rec.abort(); } catch {} };
  }, []);

  const start = () => {
    setError("");
    try { recRef.current?.start(); setListening(true); } catch { /* already started */ }
  };
  const stop = () => { try { recRef.current?.stop(); } catch {} setListening(false); };
  return { supported, listening, error, start, stop };
}

/** Read Lena's questions aloud with the browser's built-in voices. */
export function speak(text: string) {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  const voices = window.speechSynthesis.getVoices();
  const pick = voices.find((v) => /en-(CA|GB|US)/.test(v.lang) && /(Samantha|Google UK English Female|Karen|Moira|Natural|Aria|Jenny)/i.test(v.name))
    || voices.find((v) => v.lang.startsWith("en"));
  if (pick) u.voice = pick;
  u.rate = 1;
  u.pitch = 1;
  window.speechSynthesis.speak(u);
}

export function stopSpeaking() {
  if (typeof window !== "undefined" && "speechSynthesis" in window) window.speechSynthesis.cancel();
}
