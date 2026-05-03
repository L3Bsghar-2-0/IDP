import argparse
import os
import re
import json
import sys
import time
import pickle
import numpy as np
import pandas as pd
import tensorflow as tf

def create_sliding_windows(data, window_size):
    X, y = [], []
    for i in range(len(data) - window_size):
        X.append(data[i : i + window_size])
        y.append(data[i + window_size])
    return np.array(X), np.array(y)

def run_serial_mode(args):
    try:
        import serial
    except ImportError:
        print("ERROR: pyserial is required for serial mode. Install with 'pip install pyserial'")
        return

    print(f"Connecting to {args.port} at {args.baud} baud...")
    
    latencies = []
    # Match strings like "[Inference done in 45.2ms]" or "[Inference done in 45ms]"
    pattern = re.compile(r"\[Inference done in (\d+\.?\d*)ms\]", re.IGNORECASE)

    try:
        with serial.Serial(args.port, args.baud, timeout=5) as ser:
            print("Listening for inferences... (collecting 50 samples)")
            while len(latencies) < 50:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if not line:
                    continue
                # Echo device output for visibility
                print(f"Device: {line}")
                
                match = pattern.search(line)
                if match:
                    latency = float(match.group(1))
                    latencies.append(latency)
                    print(f"-> Captured latency sample {len(latencies)}/50: {latency} ms")
    except Exception as e:
        print(f"Serial error: {e}")
        if len(latencies) == 0:
            print("ERROR: No latency samples collected.")
            sys.exit(1)

    # Calculate stats
    latencies = np.array(latencies)
    mean_lat = np.mean(latencies)
    p50_lat = np.percentile(latencies, 50)
    p95_lat = np.percentile(latencies, 95)
    max_lat = np.max(latencies)

    pass_status = mean_lat < 200.0

    print("\n=== Serial Latency Results ===")
    print(f"Samples: {len(latencies)}")
    print(f"Mean: {mean_lat:.2f} ms")
    print(f"p50:  {p50_lat:.2f} ms")
    print(f"p95:  {p95_lat:.2f} ms")
    print(f"Max:  {max_lat:.2f} ms")
    print(f"Budget (< 200ms): {'PASS' if pass_status else 'FAIL'}")

    report = {
        "mode": "serial",
        "samples": len(latencies),
        "mean_inference_ms": mean_lat,
        "p50_inference_ms": p50_lat,
        "p95_inference_ms": p95_lat,
        "max_inference_ms": max_lat,
        "latency_pass": bool(pass_status)
    }

    with open("latency_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print("Saved latency_report.json")

def run_emulate_mode(args):
    # Load Model
    if not os.path.exists(args.model):
        print(f"ERROR: Model file {args.model} not found.")
        sys.exit(1)
        
    model_size_kb = os.path.getsize(args.model) / 1024.0
    interpreter = tf.lite.Interpreter(model_path=args.model)
    interpreter.allocate_tensors()

    input_details = interpreter.get_input_details()[0]
    output_details = interpreter.get_output_details()[0]

    input_scale, input_zero_point = input_details.get("quantization", (0.0, 0))
    output_scale, output_zero_point = output_details.get("quantization", (0.0, 0))
    is_input_quantized = input_scale != 0.0
    is_output_quantized = output_scale != 0.0

    try:
        df = pd.read_csv(args.data)
    except FileNotFoundError:
        print(f"ERROR: Data file not found: {args.data}")
        sys.exit(1)
    if 'timestamp' in df.columns:
        df = df.set_index('timestamp')
        
    sensor_names = list(df.columns)
    
    scaler_path = getattr(args, 'scaler_path', 'scaler.pkl')
    try:
        with open(scaler_path, "rb") as f:
            scaler = pickle.load(f)
    except FileNotFoundError:
        print(f"ERROR: Scaler file not found: {scaler_path}")
        sys.exit(1)

    scaled_data = scaler.transform(df)
    X, y = create_sliding_windows(scaled_data, args.window_size)
    
    # Anomaly tracking using rolling history
    buffer_size = 20
    error_buffer = [] 
    anomaly_events = []
    
    latencies = []
    predictions = []
    actuals = []
    
    print("Starting emulation...")
    
    for i in range(len(X)):
        input_data = X[i:i+1].astype(np.float32)
        target = y[i]
        
        start_time = time.perf_counter()
        
        # Handle manual input quantization required by full-integer TFLite models
        if is_input_quantized:
            q_input = input_data / input_scale + input_zero_point
            q_input = np.round(q_input).astype(input_details["dtype"])
        else:
            q_input = input_data
            
        interpreter.set_tensor(input_details["index"], q_input)
        interpreter.invoke()
        
        output_data = interpreter.get_tensor(output_details["index"])[0]
        
        # Dequantize predictions back to float domain
        if is_output_quantized:
            output_data = (output_data.astype(np.float32) - output_zero_point) * output_scale
        
        end_time = time.perf_counter()
        
        latency_ms = (end_time - start_time) * 1000.0
        latencies.append(latency_ms)
        
        pred = output_data
        actual = target
        error = np.abs(pred - actual)
        
        predictions.append(pred)
        actuals.append(actual)
        
        is_anomaly = False
        
        # Anomaly Detection Logic (Rolling Buffer & 2.5-Sigma Threshold)
        if len(error_buffer) >= buffer_size:
            recent_errors = np.array(error_buffer[-buffer_size:])
            means = np.mean(recent_errors, axis=0)
            stds = np.std(recent_errors, axis=0)
            
            # Compute dynamic threshold per sensor
            thresholds = means + 2.5 * stds
            
            for s_idx, (err, thresh) in enumerate(zip(error, thresholds)):
                # Adding 1e-4 epsilon to stds to prevent false triggers during totally static periods
                if err > (thresh + 1e-4):
                    is_anomaly = True
                    anomaly_events.append({
                        "window": i,
                        "sensor": sensor_names[s_idx],
                        "error": float(err),
                        "type": "spike"
                    })
        
        error_buffer.append(error)
        
        # Output terminal lines per window
        pred_str = ", ".join([f"{p:.3f}" for p in pred])
        act_str = ", ".join([f"{a:.3f}" for a in actual])
        err_str = ", ".join([f"{e:.3f}" for e in error])
        
        print(f"Window {i:04d} | predicted=[{pred_str}] | actual=[{act_str}] | error=[{err_str}] | anomaly={is_anomaly}")

    # Compute Final Stats
    latencies = np.array(latencies)
    mean_lat = np.mean(latencies)
    p95_lat = np.percentile(latencies, 95)
    
    predictions = np.array(predictions)
    actuals = np.array(actuals)
    mae_per_sensor_raw = np.mean(np.abs(predictions - actuals), axis=0)
    
    mae_per_sensor = {sensor_names[i]: float(mae_per_sensor_raw[i]) for i in range(len(sensor_names))}
    
    latency_pass = mean_lat < 200.0
    
    print("\n=== Emulation Results ===")
    print(f"Model Size: {model_size_kb:.2f} KB")
    print(f"Mean Latency: {mean_lat:.2f} ms")
    print(f"P95 Latency:  {p95_lat:.2f} ms")
    print("MAE per sensor:")
    for k, v in mae_per_sensor.items():
        print(f"  {k}: {v:.4f}")
    print(f"Total Anomalies Detected: {len(anomaly_events)}")
    
    # Save formatted JSON for the jury
    results = {
        "model_size_kb": float(model_size_kb),
        "mean_inference_ms": float(mean_lat),
        "p95_inference_ms": float(p95_lat),
        "latency_pass": bool(latency_pass),
        "mae_per_sensor": mae_per_sensor,
        "anomalies_detected": len(anomaly_events),
        "anomaly_events": anomaly_events
    }
    
    output_dir = getattr(args, 'output_dir', '.')
    os.makedirs(output_dir, exist_ok=True)

    results_path = os.path.join(output_dir, "simulation_results.json")
    try:
        with open(results_path, "w") as f:
            json.dump(results, f, indent=2)
    except Exception as e:
        print(f"ERROR: Failed to save simulation_results.json: {e}")
        sys.exit(1)
    print(f"Saved {results_path} (Jury Evidence)")
    
    # Standard latency report fallback
    latency_report = {
        "mode": "emulate",
        "samples": len(latencies),
        "mean_inference_ms": float(mean_lat),
        "p50_inference_ms": float(np.percentile(latencies, 50)),
        "p95_inference_ms": float(p95_lat),
        "max_inference_ms": float(np.max(latencies)),
        "latency_pass": bool(latency_pass)
    }
    latency_path = os.path.join(output_dir, "latency_report.json")
    try:
        with open(latency_path, "w") as f:
            json.dump(latency_report, f, indent=2)
    except Exception as e:
        print(f"ERROR: Failed to save latency_report.json: {e}")
        sys.exit(1)
    print(f"Saved {latency_path}")

def main():
    parser = argparse.ArgumentParser(description="Simulate Edge Inference and Anomaly Detection.")
    parser.add_argument("--mode", type=str, choices=["serial", "emulate"], default="emulate",
                        help="Operating mode: serial (real device) or emulate (Python TFLite interpreter)")
    parser.add_argument("--model", type=str, default="model_int8.tflite", help="Path to quantized model")
    parser.add_argument("--data", type=str, default="held_out_test.csv", help="Path to test data")
    parser.add_argument("--port", type=str, default="COM3", help="Serial port (Mode A)")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate (Mode A)")
    parser.add_argument("--window_size", type=int, default=10, help="Window size used in training")
    parser.add_argument("--scaler_path", type=str, default="scaler.pkl", help="Path to scaler.pkl")
    parser.add_argument("--output_dir", type=str, default=".", help="Output directory for results")
    args = parser.parse_args()

    if args.mode == "serial":
        run_serial_mode(args)
    elif args.mode == "emulate":
        run_emulate_mode(args)

if __name__ == "__main__":
    main()
