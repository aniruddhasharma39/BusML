import gzip
import shutil
import os

input_file = "dashboard/data.json"
output_file = "dashboard/data.json.gz"

print(f"Compressing {input_file}...")
with open(input_file, 'rb') as f_in:
    with gzip.open(output_file, 'wb') as f_out:
        shutil.copyfileobj(f_in, f_out)

print(f"Original size: {os.path.getsize(input_file) / (1024*1024):.2f} MB")
print(f"Compressed size: {os.path.getsize(output_file) / (1024*1024):.2f} MB")
