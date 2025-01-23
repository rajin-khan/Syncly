import os

#function for merging files
def merge_file(output_file, chunk_files):
    #output file to open in binary write mode
    output = open(output_file, 'wb')
    try:
        #taking each chunk from the chunk file list
        for chunk in chunk_files:
            #reading individual chunks
            input = open(chunk, 'rb')
            try:
                #writing individual chunks part in the output file
                output.write(input.read())
            finally:
                #close chunk file
                input.close()
    finally:
        #close output file
        output.close()
    #if sucessful print message
    print(f"file merged as {output_file}")

#function for file splitting
def split_file(file_path, chunk_size):
    #open file in read binary mode
    f = open(file_path, 'rb')
    try:
        file_chunk = 0
        while True:
            #creating a chunk from the original file
            chunk = f.read(chunk_size)
            
            #break condition: if no data is left to be chunked
            if not chunk:
                break

            #open the chunk in write binary mode
            chunk_file = open(f"{file_path}.part{file_chunk}.csv", 'wb')
            try:
                #write a part into the chunk file 
                chunk_file.write(chunk)
            finally:
                #close the file after writing
                chunk_file.close()
            #no of chunks increased
            file_chunk+=1
    finally:
        f.close()
    #if sucessful print message
    print(f"file split into {file_chunk} chunks")


#file path
file_path = 'csv_result-Rice_Cammeo_Osmancik new.csv'
#chunk size 10kb
chunk_size = 1024*10

#split_file(file_path,chunk_size)

# no of files divided into take this from the split function  for the actual code
file_num = 32
# outputfile for when we download, name will be taken from user in actual code
new_file = 'output.csv'

#list of chunk file names here
chunk_path_list = []

for i in range(file_num):
    # taking each individial chunk path
    chunk_name = f"csv_result-Rice_Cammeo_Osmancik new.csv.part{i}.csv"
    #if it exists append them to the list
    if os.path.exists(chunk_name):
        chunk_path_list.append(chunk_name)
    #chunk does not exist, there is an error in splitting probably
    else:
        print(f"Warning: {chunk_name} does not exist.")

merge_file(new_file,chunk_path_list)
