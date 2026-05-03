import argparse
import os
import sys
import pickle
import numpy as np
import pandas as pd
import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, Flatten, Input
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau
from sklearn.preprocessing import MinMaxScaler

# ── Reproducibility ──────────────────────────────────────────────────
SEED = 42
np.random.seed(SEED)
tf.random.set_seed(SEED)
os.environ["PYTHONHASHSEED"] = str(SEED)
os.environ["TF_DETERMINISTIC_OPS"] = "1"

def load_and_preprocess(data_path):
    print(f"Loading data from {data_path}...")
    try:
        df = pd.read_csv(data_path)
    except FileNotFoundError:
        print(f"ERROR: Data file not found: {data_path}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to read CSV: {e}")
        sys.exit(1)
    
    # Keep only necessary columns if present
    # Expecting: timestamp, sensor_type, value
    if 'timestamp' not in df.columns or 'sensor_type' not in df.columns or 'value' not in df.columns:
        raise ValueError("CSV must contain 'timestamp', 'sensor_type', and 'value' columns.")
        
    print("Pivoting data...")
    # Pivot so each sensor type becomes its own column
    df_pivot = df.pivot_table(index='timestamp', columns='sensor_type', values='value')
    
    print("Sorting and interpolating...")
    df_pivot = df_pivot.sort_index()
    # linear interpolation for short gaps (max 3 consecutive)
    df_pivot = df_pivot.interpolate(method='linear', limit=3)
    # Drop any remaining NaNs (like at the beginning/end or gaps > 3)
    df_pivot = df_pivot.dropna()
    
    return df_pivot

def create_sliding_windows(data, window_size):
    X, y = [], []
    for i in range(len(data) - window_size):
        X.append(data[i : i + window_size])
        # predict the next timestep for all sensors
        y.append(data[i + window_size])
    return np.array(X), np.array(y)

def main():
    parser = argparse.ArgumentParser(description="Train TinyML model for sensor anomaly detection.")
    parser.add_argument("--data_path", type=str, required=True, help="Path to the unified sensor CSV.")
    parser.add_argument("--window_size", type=int, default=10, help="Sliding window size (N timesteps).")
    parser.add_argument("--output_dir", type=str, default=".", help="Directory for output files.")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    
    # 1. DATA PREP
    df_pivot = load_and_preprocess(args.data_path)
    print(f"Preprocessed data shape: {df_pivot.shape}")
    
    # Chronological Split: 70% train / 15% val / 15% test
    n = len(df_pivot)
    train_end = int(n * 0.7)
    val_end = int(n * 0.85)
    
    train_df = df_pivot.iloc[:train_end]
    val_df = df_pivot.iloc[train_end:val_end]
    test_df = df_pivot.iloc[val_end:]
    
    # Save held out test split
    test_path = os.path.join(args.output_dir, "held_out_test.csv")
    try:
        test_df.to_csv(test_path)
        print(f"Saved {test_path} (Jury evaluation set)")
    except Exception as e:
        print(f"ERROR: Failed to save held_out_test.csv: {e}")
        sys.exit(1)
    
    # Scale Data (fit on train only to prevent data leakage)
    scaler = MinMaxScaler()
    train_scaled = scaler.fit_transform(train_df)
    val_scaled = scaler.transform(val_df)
    test_scaled = scaler.transform(test_df)
    
    # Save scaler
    scaler_path = os.path.join(args.output_dir, "scaler.pkl")
    try:
        with open(scaler_path, "wb") as f:
            pickle.dump(scaler, f)
        print(f"Saved {scaler_path}")
    except Exception as e:
        print(f"ERROR: Failed to save scaler.pkl: {e}")
        sys.exit(1)
    
    # Create sliding windows
    X_train, y_train = create_sliding_windows(train_scaled, args.window_size)
    X_val, y_val = create_sliding_windows(val_scaled, args.window_size)
    X_test, y_test = create_sliding_windows(test_scaled, args.window_size)
    
    print(f"X_train shape: {X_train.shape}, y_train shape: {y_train.shape}")
    
    num_sensors = X_train.shape[2]
    
    # 2. MODEL ARCHITECTURE (TinyML-compatible MLP)
    # Using MLP, targeting < 5000 params, no BatchNorm, Linear output
    model = Sequential([
        Input(shape=(args.window_size, num_sensors)),
        Flatten(),
        Dense(32, activation='relu'),
        Dense(16, activation='relu'),
        Dense(num_sensors, activation='linear')
    ])
    
    model.summary()
    total_params = model.count_params()
    if total_params >= 5000:
        print(f"WARNING: Total parameters ({total_params}) >= 5000! Quantization might be tight.")
    else:
        print(f"SUCCESS: Total parameters ({total_params}) is well under the 5000 limit.")
    
    # 3. TRAINING
    model.compile(optimizer=Adam(learning_rate=0.001), loss='mae')
    
    callbacks = [
        EarlyStopping(monitor='val_loss', patience=10, restore_best_weights=True),
        ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=5, min_lr=1e-5)
    ]
    
    print("Starting training...")
    history = model.fit(
        X_train, y_train,
        validation_data=(X_val, y_val),
        epochs=100,
        batch_size=32,
        callbacks=callbacks,
        verbose=1
    )
    
    # Evaluate
    train_mae = model.evaluate(X_train, y_train, verbose=0)
    val_mae = model.evaluate(X_val, y_val, verbose=0)
    test_mae = model.evaluate(X_test, y_test, verbose=0)
    
    print(f"Final Train MAE: {train_mae:.4f}")
    print(f"Final Val MAE:   {val_mae:.4f}")
    print(f"Final Test MAE:  {test_mae:.4f}")
    
    # 4. OUTPUT FILES
    model_path = os.path.join(args.output_dir, "model.h5")
    try:
        model.save(model_path)
        print(f"Saved {model_path}")
    except Exception as e:
        print(f"ERROR: Failed to save model: {e}")
        sys.exit(1)
    
    report_path = os.path.join(args.output_dir, "training_report.txt")
    try:
        with open(report_path, "w") as f:
            f.write("=== TinyML Model Training Report ===\n")
            f.write(f"Architecture: MLP\n")
            f.write(f"Window Size: {args.window_size}\n")
            f.write(f"Number of Sensors: {num_sensors}\n")
            f.write(f"Total Parameters: {total_params}\n")
            f.write("-" * 30 + "\n")
            f.write(f"Final Train MAE: {train_mae:.4f}\n")
            f.write(f"Final Val MAE:   {val_mae:.4f}\n")
            f.write(f"Final Test MAE:  {test_mae:.4f}\n")
            f.write("-" * 30 + "\n")
            
            # Test MAE per sensor
            preds = model.predict(X_test, verbose=0)
            # Calculate MAE for each sensor
            sensor_maes = np.mean(np.abs(preds - y_test), axis=0)
            sensor_names = df_pivot.columns
            f.write("Test MAE per sensor (scaled values):\n")
            for name, smae in zip(sensor_names, sensor_maes):
                f.write(f"  {name}: {smae:.4f}\n")
    except Exception as e:
        print(f"ERROR: Failed to save training report: {e}")
        sys.exit(1)

    print(f"Saved {report_path}")
    print(f"Final test MAE: {test_mae:.4f}")

if __name__ == "__main__":
    main()
