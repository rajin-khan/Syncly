import os

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

split_file(file_path,chunk_size)