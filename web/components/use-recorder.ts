import { useRef, useState } from "react";

// What the customer answered when the browser asked for the microphone, on this page load.
export type MicrophoneAccess = "not asked" | "granted" | "denied";

// Push-to-talk: `start` opens the microphone, `stop` closes it and resolves with the recording.
// `allow` only asks for the permission, so the customer can grant it before the first message.
export function useRecorder() {
  const recorder = useRef<MediaRecorder | null>(null);
  const [recording, setRecording] = useState(false);
  const [access, setAccess] = useState<MicrophoneAccess>("not asked");

  async function open() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      setAccess("granted");
      return stream;
    } catch (error) {
      setAccess("denied"); // refused, or no microphone: the caller shows the browser's reason
      throw error;
    }
  }

  function close(stream: MediaStream) {
    stream.getTracks().forEach((track) => track.stop()); // turns the browser's mic light off
  }

  async function allow() {
    close(await open());
  }

  async function start() {
    recorder.current = new MediaRecorder(await open());
    recorder.current.start();
    setRecording(true);
  }

  function stop() {
    return new Promise<Blob>((resolve) => {
      const current = recorder.current!;
      current.ondataavailable = (event) => resolve(event.data); // one chunk: start() had no timeslice
      current.stop();
      close(current.stream);
      setRecording(false);
    });
  }

  return { access, allow, recording, start, stop };
}
