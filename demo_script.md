# Live Pitch Demo Script (90 Seconds)

**Speaker Instructions:** Keep pace rapid. Emphasize the keywords "offline", "INT8", and "latency".

---

**(T+0s): Start Emulation**
*Action:* Open terminal and run: `python simulate.py --mode emulate --model model_int8.tflite --data held_out_test.csv`
*Speaker:* "To prove our pipeline's robustness for Track A, we are initializing the emulator which mirrors the exact ESP32 TFLite Micro environment. Here is the offline stream processing live."

**(T+15s): Highlight Latency**
*Action:* Point to the terminal output lines displaying inference times and errors.
*Speaker:* "Notice the inference times. Our hard requirement was sub-200 milliseconds. We are consistently hitting `[MEAN_LATENCY_MS]` ms per window, leaving the microcontroller completely free to handle other RTOS tasks."

**(T+30s): Inject Synthetic Spike**
*Action:* Pre-modify a single window in the CSV or highlight the naturally occurring spike that triggers the anomaly boolean in the terminal.
*Speaker:* "Watch the anomaly detector. As the incoming data spikes, our rolling 2.5-sigma threshold immediately catches the deviation. The system logs `anomaly=True`. No cloud round-trip—this is purely on-device detection."

**(T+60s): Display JSON Evidence**
*Action:* Open `simulation_results.json` in the IDE. Highlight the final block.
*Speaker:* "All validation data is securely logged. Here is our `simulation_results.json`, which tracks our strict size and latency metrics, alongside exactly `[ANOMALY_COUNT]` captured anomaly events for the jury to evaluate."

**(T+75s): Prove Model Size**
*Action:* Run `ls -lh model_int8.tflite` in the terminal to display the file size.
*Speaker:* "Finally, memory footprint. Our absolute target was to fit within 520KB SRAM and 4MB Flash. By utilizing INT8 quantization, our total binary model size sits at exactly `[MODEL_SIZE_KB_INT8]` KB. Tiny, fast, and completely offline. Thank you."
