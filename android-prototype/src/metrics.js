// Session metrics: every wake / commit / timeout / camera interval is
// queued in localStorage and flushed in the background to the server's
// POST /log (Neon Postgres). Nothing blocks the UI; failed flushes retry.

import { Device } from "@capacitor/device";
import { Capacitor } from "@capacitor/core";
import { API_URL } from "./config";

const QUEUE_KEY = "dusk_log_queue_v1";
const DEVICE_KEY = "dusk_device_id";
const FLUSH_MS = 20000;
const BATCH = 100;

let deviceTag = null;
let flushing = false;

async function deviceId() {
  if (deviceTag) return deviceTag;
  let id = localStorage.getItem(DEVICE_KEY);
  if (!id) {
    id = Math.random().toString(36).slice(2, 8);
    localStorage.setItem(DEVICE_KEY, id);
  }
  try {
    const info = await Device.getInfo();
    deviceTag = `${info.model || "web"}-${id}`;
  } catch {
    deviceTag = `web-${id}`;
  }
  return deviceTag;
}

async function batteryLevel() {
  try {
    if (Capacitor.isNativePlatform()) {
      const info = await Device.getBatteryInfo();
      return Math.round((info.batteryLevel ?? -1) * 100);
    }
    if (navigator.getBattery) {
      const b = await navigator.getBattery();
      return Math.round(b.level * 100);
    }
  } catch { /* no battery info available */ }
  return -1;
}

const readQueue = () => JSON.parse(localStorage.getItem(QUEUE_KEY) || "[]");
const writeQueue = (q) => localStorage.setItem(QUEUE_KEY, JSON.stringify(q));

export async function logEvent(event, data = {}) {
  const row = {
    ts: new Date().toISOString(),
    event,
    battery: await batteryLevel(),
    ...data,
  };
  writeQueue([...readQueue(), row]);
  console.log("[metrics]", row);
  return row;
}

export async function flush() {
  if (flushing) return;
  const queue = readQueue();
  if (!queue.length) return;
  flushing = true;
  try {
    const batch = queue.slice(0, BATCH);
    const res = await fetch(`${API_URL}/log`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device: await deviceId(), events: batch }),
    });
    if (res.ok) {
      writeQueue(readQueue().slice(batch.length));
      console.log(`[metrics] flushed ${batch.length} events`);
    }
  } catch {
    // offline — keep the queue, retry next tick
  } finally {
    flushing = false;
  }
}

export function startMetricsFlusher() {
  flush();
  const timer = setInterval(flush, FLUSH_MS);
  return () => clearInterval(timer);
}

export const pendingCount = () => readQueue().length;
