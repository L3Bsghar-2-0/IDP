# Slide: Edge Intelligence — offline anomaly detection on ESP32

## Box 1: Architecture
* **Model Type:** Multi-Layer Perceptron (MLP) mapping 10-timestep sliding windows directly to next-step multi-sensor outputs.
* **Compression Method:** Post-training fully-integer (INT8) quantization via the TFLite Converter to radically minimize footprint.
* **Deployment Method:** Serialized C++ byte array (`model_data.h`) flashed directly to ESP32 Flash via Arduino IDE with TFLite Micro.

## Box 2: Key Numbers
* **Model Size:** `[MODEL_SIZE_KB_INT8]` KB *(Budget < 200 KB)*
* **Mean Latency:** `[MEAN_LATENCY_MS]` ms *(Budget < 200 ms)*
* **Test MAE:** `[MEAN_TEST_MAE]`
* **Anomalies Detected:** `[ANOMALY_COUNT]` *(in held-out simulation test set)*

## Box 3: Live Demo Description
During the demo, the jury will observe the live simulation parsing the data stream offline. We will intentionally trigger a sensor spike in the dataset, and the terminal will instantly log `anomaly=True` alongside the specific error magnitude. The output distinctly proves that the device acts independently, isolating anomalies in under `[MEAN_LATENCY_MS]` milliseconds per step.

## Box 4: What We'd Do With More Time
* **Quantization-Aware Training:** Integrate QAT during the `train_model.py` phase to squeeze out the final <5% accuracy degradation commonly introduced by INT8 post-training conversion.
* **Multi-Sensor LSTM/1D-CNN:** Upgrade the architecture to lightweight recurrent networks or 1D convolutions to better capture complex temporal sequence dependencies across variables.
* **OTA Model Updates:** Utilize the ESP32's WiFi capabilities to fetch updated INT8 `.tflite` weights dynamically via MQTT over-the-air, eliminating the need to physically re-flash the hardware for iterations.
