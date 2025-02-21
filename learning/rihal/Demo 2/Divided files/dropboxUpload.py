import dropbox
import os
import uuid

#Replace with your Dropbox access token
ACCESS_TOKEN = 'sl.u.AFjHTnowCQTAxd0KB0U8DtIMj43kgGTbrLatoRcWMBO6j8nFAL0KaP9qY83ITdbDwOF3fSgq8yaCZK2Zu907EZEfwsBKAWwBi6MBj8HwVBK34OOooJyZhS7WghboRBDbKimCssmhNrAcTC5Ztddh0GyBNqhVqwDsvu0XtEepS7d-TcK7uToELzUi4BIOLrtw7m5OIvT6sY7CDbPjifUWZ-j5UwZqZqgBWv1pK5AzZUmX-lTZ1cai1V1Uyvc5TbXstuy9TjR2EPvFwBsFpUi6iKaZRhsM00ET-NVppCvcZRRsrPZLUKxVgZCF217c-8iXHjF-Ytjxxb_6-PkTB1dOu8q0jaHozvL094vxipTo00xFJfn6kVL25cO28674yU1t0gX56_rqGkx9EUFHSfPozJAtcc_EjEPZRXlZBFx4Cl_SIP_EkScVjVd5MJ30AbmAi0OS6ZnQ-qJUOlhnJZffq93ZQf6B1sZ-PZltS2qrf87oeiZ8OnlskTAfgaunRTS1eDlkfPfw00CH9UpsXt7qfLP2fwSEjPphtRpYZbJ7jVgt05bzFUnKFhoekpZ1t9xO5Q9X-Tp7oxolNeOWHgnlyqXahURjZufelAr8kVarVbdKJfBsD7XXwMAq-A8HpBrL7Fpw9tzkb120rjm35So6qG872OgiXfawJYNFtVic8NmCv8B9J9CYbriwGKkTLYL8vCw94lnGBIqZ5Ocp8WvDTHklema8P2diIv9bmn0DW-qHq9vJ8Vvjwn6Orhxa6wRx4YPsXDjlPhq665QqirZe6CHMhcHHIQC61BPZbSj2nUF1hylf8w-2dcWLuvqpAkXvvr65SX-8gH5yhns6dipkuitL1fMglADgflFG_xzmQghFXEX-i0xxpXNmzSGJVLn1p_4J7aogM1Mj4pDisQmsfbpuMuevl8Q7KIc7LQdaeoj4XhGGl4riFzfuINGSqIDaxPP1lq__8MoZOkmOnuB-25Xkd5M9PBYkd63rQmjlUKGdaZqRcfO0yLwxSB5vzdBRg2rTd8snrxorXoT8AGLdYEkQ74ld-OAoA11kyijTDuAF-4ak6OhPwm5ZVlp8-wSLY1W0aaUSRVoeoPWiplmHGJpA0-mBgPjubUSieUwoApAGW2rgLTthaA-KvpYaCo4VUqT6bCP5ZdHgM65lc-Elx4xI1eCaU9r2pLixegUVf664_hGS6LQKRvDd6eTtE_NHNiCRkxQLipeSu6awpjkuEH4tuJKTxo-m9-h7qdEj5VtCQG2kO59ayjAzrhuBSbRRdGt967yo2WpvKdhm8lCcO7te7c9jMqXfJcswxgx6AImH_twidujMmbSHh1qQoqWV52wEW-aukKMq4B6ToyvdA54WdUQ8vzQSsgD3jwItezkz_2GvSbY9o5cKEAkxsm5VrSNtAdWtSi1tHksO89GJueFl2i1oAwpW0en-J8m9tBpXVA'.strip()

def upload_file_to_dropbox(file_path):
    #Initialize Dropbox client
    dbx = dropbox.Dropbox(ACCESS_TOKEN)

    try:
        #Remove any extra quotes or whitespace from the file path
        file_path = file_path.strip('"\'')  # Strip both single and double quotes

        #Check if the file exists
        if not os.path.exists(file_path):
            print(f"Error: The file {file_path} does not exist.")
            return

        file_name = os.path.basename(file_path)  #Get the file name from the file path
        dropbox_path = f"/{file_name}"  #Create a random path in Dropbox

        #Open the file and upload it
        with open(file_path, 'rb') as f:
            dbx.files_upload(f.read(), dropbox_path, mode=dropbox.files.WriteMode.overwrite)
            print(f"File {file_path} uploaded to Dropbox at: {dropbox_path}")
    except dropbox.exceptions.ApiError as err:
        print(f"API error: {err}")
    except Exception as e:
        print(f"Error uploading file: {e}")

def search_and_download_file(file_name):
    #Initialize Dropbox client
    dbx = dropbox.Dropbox(ACCESS_TOKEN)

    try:
        #Search for files in Dropbox
        result = dbx.files_search_v2("", file_name).matches

        if not result:
            print(f"No files found with the name '{file_name}'.")
            return

        #Iterate through search results
        for match in result:
            metadata = match.metadata
            if isinstance(metadata, dropbox.files.FileMetadata):
                #Check if the file name (without extension) matches the search term
                dbx_file_name = os.path.splitext(metadata.name)[0]
                if dbx_file_name.lower() == file_name.lower():
                    print(f"Found file: {metadata.name}")
                    #Download the file
                    download_path = f"./{metadata.name}"
                    with open(download_path, "wb") as f:
                        metadata, res = dbx.files_download(metadata.path_lower)
                        f.write(res.content)
                    print(f"File downloaded to: {download_path}")
                    return

        print(f"No exact match found for '{file_name}'.")
    except dropbox.exceptions.ApiError as err:
        print(f"API error: {err}")
    except Exception as e:
        print(f"Error downloading file: {e}")

if __name__ == "__main__":
    while True:
        print("\n1. Upload a file to Dropbox")
        print("2. Search and download a file from Dropbox")
        print("3. Exit")
        choice = input("Enter your choice (1/2/3): ")

        if choice == "1":
            #Upload a file
            file_path = input("Enter the path to the file you want to upload (with or without quotes): ")
            upload_file_to_dropbox(file_path)
        elif choice == "2":
            #Search and download a file
            file_name = input("Enter the file name (without extension) to search and download: ")
            search_and_download_file(file_name)
        elif choice == "3":
            print("Exiting...")
            break
        else:
            print("Invalid choice. Please try again.")
