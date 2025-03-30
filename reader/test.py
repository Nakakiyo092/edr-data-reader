import shutil
import csv

# File paths for source and destination
source_file = "format/did_fa13.csv"
destination_file = "result/did_fa13.csv"

# Copy the file
try:
    shutil.copy(source_file, destination_file)
    print(f"The file '{source_file}' has been successfully copied to '{destination_file}'.")
except FileNotFoundError:
    print(f"The source file '{source_file}' does not exist.")
except PermissionError:
    print("You do not have the necessary permissions to read or write the file.")
except Exception as e:
    print(f"An error occurred: {e}")

# Make data
byte_array = bytearray([1] * 772)

# Read the input CSV file and write to the output file with the additional column
try:
    with open(source_file, mode="r", encoding="utf-8") as infile, open(destination_file, mode="w", encoding="utf-8", newline="") as outfile:
        reader = csv.reader(infile)
        writer = csv.writer(outfile)
        
        # Read header and add new column name
        header = next(reader)
        header.append("Raw value")  # Add a new column named 'Raw value'
        writer.writerow(header)
        
        # Process rows
        for row in reader:
            no = int(row[0])  # Convert No column to integer
            if 1 <= no <= len(byte_array):  # Check if No is within the range
                row.append(byte_array[no - 1])  # Add corresponding byte array value
            else:
                row.append("N/A")  # Handle cases where No is out of range
            writer.writerow(row)
    
    print(f"The file '{destination_file}' has been successfully created with the additional column.")
except FileNotFoundError:
    print(f"The input file '{source_file}' does not exist.")
except Exception as e:
    print(f"An error occurred: {e}")
