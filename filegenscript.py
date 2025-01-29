import os
import random
import string
import json
import csv

def create_binary_file(filename, size_in_mb):
    size_in_bytes = size_in_mb * 1024 * 1024 #convert the given size to bytes
    with open(filename, 'wb') as f:
        f.write(os.urandom(size_in_bytes))  #random binary data

def create_text_file(filename, size_in_mb):
    size_in_bytes = size_in_mb * 1024 * 1024
    chars = string.ascii_letters + string.digits + " "
    with open(filename, 'w') as f:
        while f.tell() < size_in_bytes:
            f.write(''.join(random.choices(chars, k=1024)) + "\n") #random text file

def create_json_file(filename, num_entries):
    data = []
    for _ in range(num_entries):
        data.append({
            "name": ''.join(random.choices(string.ascii_letters, k=8)),
            "age": random.randint(18, 75),
            "email": ''.join(random.choices(string.ascii_letters, k=5)) + "@example.com"
        })
    
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)

def create_csv_file(filename, num_rows):
    headers = ["ID", "Name", "Age", "Email"]
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for i in range(1, num_rows + 1):
            writer.writerow([i, ''.join(random.choices(string.ascii_letters, k=8)), random.randint(18, 60), 
                             ''.join(random.choices(string.ascii_letters, k=5)) + "@example.com"])

def generate_dummy_file(filename, file_type, size, output_dir="./dummy_files"): #creates the file we want in the specified directory, relative to the script
    
    os.makedirs(output_dir, exist_ok=True) #creates directory
    file_path = os.path.join(output_dir, filename)

    print(f"Creating: {file_path} ({size} {'MB' if file_type in ['binary', 'text'] else 'entries'})...") #to ensure everything works normally

    if file_type == "binary":
        create_binary_file(file_path, size)
    elif file_type == "text":
        create_text_file(file_path, size)
    elif file_type == "json":
        create_json_file(file_path, size)
    elif file_type == "csv":
        create_csv_file(file_path, size)
    else:
        print(f"❌ Unsupported file type: {file_type}") #error handling
        return

    print(f"✅ File created successfully: {file_path}") #success message

# Example Usage:
if __name__ == "__main__":  # 50MB binary file
    generate_dummy_file("dummy_text.txt", "text", 100) #100MB text file, as an example
    '''
        other examples of file creation:
        generate_dummy_file("dummy_data.json", "json", 1000)  # 1000 JSON entries
        generate_dummy_file("dummy_spreadsheet.csv", "csv", 500)  # 500 CSV rows
    '''
