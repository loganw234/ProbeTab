// The rehearsal page's script, run inside the bench page's frame: it puts the rehearsal's
// stand-in where the browser's WebUSB would be, before Connect is pressed, and tells the
// rehearsal page what the simulated LabPro has done. app/bench/rehearse.html adds it to the
// frame each time the frame loads; nothing in the bench page itself names it.

import { FIXTURES } from "./generated/fixtures.ts";
import { RehearsalUsb, SCRIPT } from "./rehearsal-device.ts";

/** Shows text on the rehearsal page, above the frame. */
function tell(text: string): void {
  window.parent.postMessage({ rehearsal: text }, window.location.origin);
}

const fixture = FIXTURES[SCRIPT];
if (fixture === undefined) {
  tell(`refused: the generated fixtures have no ${SCRIPT}; run python tools/generate.py, then build again`);
} else {
  const total = fixture.transfers.length;
  const usb = new RehearsalUsb(fixture);
  Object.defineProperty(navigator, "usb", { value: usb, configurable: true });
  let stopped = false;
  let watched = false;
  let said = "";
  const report = (): void => {
    const labPro = usb.device?.labPro;
    if (labPro !== undefined && !watched) {
      watched = true;
      void labPro.finished.then(() => {
        stopped = true;
      });
    }
    const done = labPro === undefined ? 0 : total - labPro.remaining.length;
    let text: string;
    if (labPro === undefined) {
      text = `the simulated LabPro is plugged in: press Connect; its script holds ${total} transfers`;
    } else if (labPro.mismatch !== null) {
      text = `the simulated LabPro stopped after ${done} of ${total} transfers: ${labPro.mismatch}`;
    } else if (labPro.remaining.length === 0) {
      text = `the script is done: all ${total} transfers replayed, and the simulated LabPro answers nothing more`;
    } else if (stopped) {
      text = `the simulated LabPro stopped waiting after ${done} of ${total} transfers; reload for a fresh one`;
    } else {
      text = `${done} of ${total} transfers replayed`;
    }
    if (text !== said) {
      said = text;
      tell(text);
    }
  };
  report();
  setInterval(report, 250);
}
