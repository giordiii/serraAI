// Gli orari arrivano dal digital twin (ora simulata, fuso Europe/Rome).
const TZ = "Europe/Rome";

export const simTime = (iso) => iso
  ? new Date(iso).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit", timeZone: TZ }) : "—";

export const simDateTime = (iso) => iso
  ? new Date(iso).toLocaleString("it-IT", { weekday: "short", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", timeZone: TZ }) : "—";

export const simDate = (iso) => iso
  ? new Date(iso.length <= 10 ? iso + "T12:00:00" : iso).toLocaleDateString("it-IT", { day: "2-digit", month: "short", timeZone: TZ }) : "—";
