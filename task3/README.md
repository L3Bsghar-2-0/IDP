# Re·Tech Fusion — Part 3 Submission

## Track A — Edge Inference & On-Device Anomaly Detection

## Architecture Overview
The system captures raw sensor data (e.g., CO2, Temperature, Power) which is processed into a sliding window buffer directly on the edge node. The ESP32 firmware feeds this local window into a strictly offline, INT8-quantized TensorFlow Lite Multi-Layer Perceptron (MLP) to predict the expected values for the next timestep. The prediction error is then fed into a dynamic rolling z-score algorithm. If the error exceeds our 2.5-sigma threshold, the firmware raises a local anomaly flag which can subsequently be transmitted upstream via MQTT. The entire inference process operates locally without requiring any cloud compute.

## Model Details

| Metric | Value |
| --- | --- |
| **Architecture** | 1D sliding window MLP (Flatten → Dense 32 → Dense 16 → Dense) |
| **Total Parameters** | [PARAM_COUNT] (~1,500) |
| **Size FP32 (Original)** | [SIZE_FP32_KB] KB |
| **Size INT8 (Quantized)**| [SIZE_INT8_KB] KB |
| **MAE (Test Set - CO2)** | [MAE_SENSOR_1] |
| **MAE (Test Set - Temp)**| [MAE_SENSOR_2] |
| **MAE (Test Set - Pwr)** | [MAE_SENSOR_3] |

## Deployment Instructions

1. **Clone the Repository**: Ensure all firmware source files and `model_data.h` are accessible locally.
2. **Install Dependencies**: Install the Arduino IDE or PlatformIO. Install the required `TensorFlowLite_ESP32` library.
3. **Configure the Board**: Select "ESP32 Dev Module" as the target board in your IDE.
4. **Compile and Flash**: Connect the ESP32 via USB and compile/upload the sketch.
5. **Monitor Output**: Open the Serial Monitor (115200 baud) to view the initialization, buffer buildup, and live inference latency logs.

## Latency Evidence

**Target vs. Actual:**
- Target Latency: < 200 ms
- Mean Latency: `[MEAN_LATENCY_MS]` ms
- **Status:** `[PASS/FAIL]`

**Excerpt from `latency_report.json`:**
```json
{
  "mode": "serial",
  "samples": 50,
  "mean_inference_ms": [MEAN_LATENCY_MS],
  "p50_inference_ms": [P50_LATENCY_MS],
  "p95_inference_ms": [P95_LATENCY_MS],
  "max_inference_ms": [MAX_LATENCY_MS],
  "latency_pass": true
}
```

## Anomaly Detection Logic

Our on-device anomaly detection leverages a purely local **rolling buffer z-score** mechanism. The ESP32 maintains a buffer of the last 20 absolute errors calculated between the model's prediction and the actual incoming sensor reading. For every new reading, the mean and standard deviation of this historical buffer are calculated on the fly. A dynamic threshold is set at `Mean + 2.5 * Standard Deviation`. If the immediate error surpasses this threshold, a "spike" is identified and the anomaly flag is raised instantly.

*Triggered Example (from `simulation_results.json`):*
```json
{
  "window": [WINDOW_INDEX],
  "sensor": "[SENSOR_NAME]",
  "error": [ERROR_VALUE],
  "type": "spike"
}
```

## How to Reproduce

Execute the following commands sequentially to recreate the pipeline from scratch:
```bash
python train_model.py --data_path unified_sensor_data.csv --window_size 10
python convert_model.py --model model.h5 --data_path held_out_test.csv
python simulate.py --mode emulate --model model_int8.tflite --data held_out_test.csv
```

## File Index

| File | Description |
| --- | --- |
| `train_model.py` | Prepares the sliding-window dataset and trains the base Keras MLP model. |
| `convert_model.py` | Handles INT8 post-training quantization, accuracy evaluation, and C-header generation. |
| `simulate.py` | Generates jury evidence logs via local TFLite emulation or real ESP32 serial monitoring. |
| `model_data.h` | The INT8 quantized model serialized as a C byte array for ESP32 firmware inclusion. |
| `scaler.pkl` | The MinMax scaling parameters fitted on the training set for normalization. |
| `latency_report.json` | Statistical evidence proving the on-device inference latency budget is met. |
| `simulation_results.json`| Detailed JSON log output containing model metadata and isolated anomaly events. |
