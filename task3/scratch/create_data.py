import csv
import math
import random
from datetime import datetime, timedelta

# Create synthetic sensor data for TinyML pipeline testing using only stdlib
random.seed(42)
n_samples = 1000
start_time = datetime(2024, 5, 1, 12, 0, 0)

with open('task3/data/sensor_data.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['timestamp', 'sensor_type', 'value'])
    
    for i in range(n_samples):
        ts = (start_time + timedelta(seconds=i*5)).strftime('%Y-%m-%d %H:%M:%S')
        
        # Normal patterns
        temp = 25.0 + math.sin(i / 50.0) * 2.0 + random.gauss(0, 0.1)
        hum = 50.0 + math.cos(i / 40.0) * 5.0 + random.gauss(0, 0.5)
        gas = 200 + random.gauss(0, 10)
        
        # Inject some anomalies
        if 500 < i < 510:
            gas += 800  # Smoke spike
        if 800 < i < 805:
            temp += 10  # Heat spike
            
        writer.writerow([ts, 'dht22_temp', temp])
        writer.writerow([ts, 'dht22_humidity', hum])
        writer.writerow([ts, 'mq2_gas', gas])

print("Synthetic sensor_data.csv created in task3/data/ using stdlib.")
