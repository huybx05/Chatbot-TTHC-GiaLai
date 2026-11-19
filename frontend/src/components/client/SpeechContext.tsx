import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { synthesizeSpeech } from "../../api/tts";

interface SpeechContextValue {
  playingId: string | null;
  loadingId: string | null;
  error: string;
  channel: SpeechChannel;
  play: (messageId: string, text: string) => Promise<void>;
  stop: () => void;
}

export type SpeechChannel = "screen" | "voice";

const SpeechContext = createContext<SpeechContextValue | null>(null);

export function useSpeech(): SpeechContextValue | null {
  return useContext(SpeechContext);
}

/**
 * Một audio dùng chung cho cả khung chat.
 *
 * Nếu mỗi MessageAnswer tự giữ Audio riêng, người dùng có thể bấm hai câu
 * và nghe hai giọng chồng lên nhau. Provider này dừng audio cũ trước khi phát
 * audio mới và dọn object URL khi kết thúc.
 */
export function SpeechProvider({
  children,
  channel = "screen",
}: {
  children: ReactNode;
  channel?: SpeechChannel;
}) {
  const [playingId, setPlayingId] = useState<string | null>(null);
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [error, setError] = useState("");

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = useRef("");
  const controllerRef = useRef<AbortController | null>(null);
  const requestRef = useRef(0);

  const stop = useCallback(() => {
    requestRef.current += 1;
    controllerRef.current?.abort();
    controllerRef.current = null;
    audioRef.current?.pause();
    audioRef.current = null;
    if (audioUrlRef.current) {
      URL.revokeObjectURL(audioUrlRef.current);
      audioUrlRef.current = "";
    }
    setPlayingId(null);
    setLoadingId(null);
  }, []);

  const play = useCallback(
    async (messageId: string, text: string) => {
      if (!text.trim()) return;
      if (playingId === messageId) {
        stop();
        return;
      }

      stop();
      const requestId = requestRef.current;
      const controller = new AbortController();
      controllerRef.current = controller;
      setLoadingId(messageId);
      setError("");

      try {
        const blob = await synthesizeSpeech(text, controller.signal);
        if (requestRef.current !== requestId) return;

        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        audioRef.current = audio;
        audioUrlRef.current = url;
        audio.onended = () => {
          URL.revokeObjectURL(url);
          if (audioUrlRef.current === url) audioUrlRef.current = "";
          if (audioRef.current === audio) audioRef.current = null;
          setPlayingId(null);
        };
        audio.onerror = () => {
          setError("Không phát được âm thanh.");
          setPlayingId(null);
        };

        await audio.play();
        if (requestRef.current !== requestId) {
          audio.pause();
          URL.revokeObjectURL(url);
          return;
        }
        setLoadingId(null);
        setPlayingId(messageId);
      } catch (err) {
        if (controller.signal.aborted) return;
        setLoadingId(null);
        setError(
          err instanceof Error
            ? err.message
            : "Không tạo được âm thanh cho câu trả lời này.",
        );
      }
    },
    [playingId, stop],
  );

  useEffect(() => () => stop(), [stop]);

  return (
    <SpeechContext.Provider value={{ playingId, loadingId, error, channel, play, stop }}>
      {children}
    </SpeechContext.Provider>
  );
}
