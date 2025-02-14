import dropbox
import os

#Replace with your Dropbox access token
ACCESS_TOKEN = 'sl.u.AFj1ziT4xpepUHBy0CG3yPsdqahy2okrSLct7Gt1polFEbvMzfx6MOBXqJLzyDMXlldOQpuo9q0bR_A24NiGbD4bcktLRbi\
    SWBY5BENllQEJtvcEFab1t9jvZoaIl65f6spsu9tAEoEW9CrP3fCc1iQYvEGv7zUaHs1u82GgxNMLjv0z23RpxgooLBJaQRLFvEWwgPCd77Rv0nb_k1\
        jpr8VBHVkNhLqfb2kBsKnlPUo73HAE9lOh9SalYADyUUeJoIjVgRmUsKwslMqysyc2VA4I9o1ug0Fv7ldOBZ_-9WkaZSwPm54FObZpD_i0M8uO5az\
            yKWdwNtanu8Z3zRDIlZeYPtiaLBsHGhTUzsiEjQaf1hDC_ZpwnBkhp0ZswAZUa68mOrjXALwtZKG9bBjDxrm5BV-T572ZaRUpxcsVcpe9m4J8dH\
                drXkwqduGInZJl4-rt94tf9j1so00eITktNEIlOshwwIx6C0RPTZQvQIq9ncqAYCMlJa5uDaBMOuiuD3CpyrZfVSDtYD8VGjDidVCzfF8nmz\
                    1-LLa9BURDSjRQjSz8cuMpyoX6eos7QDmE9W_MW7CzEn-2UPpDLW2CoTD_kdqE4XGi23o75mbbtW3sgca27N9evmqd_ISSwxx3NFSZ7_7\
                        VNYpCLanTWa2HdDEOEnNEvJCC8F-p9HJ6M2yduzAi_J0vasxG4dJ0WpfVZBscq7C7VlcY3o0vEvHoqnuIq1tXKl52ud_omwsnchpQQL\
                            F2BiRn7Qgy0xR7QlvbF_0RnYCg-2LGnID8zGjlHqYXQ9xScRSm1piZAAEkFwxLvK-0S6bgkEZRqgcOVzAjBqHTtrfkBwTE512KaTeaT\
                                hVgGRBSE3tJCEwQT6gqZ-rIKxxd3Lf1PzuFqzq35CdpgWdcV8BIuWsQADJWotw8MY6D3bZnYPCOChsiWPSQGqFFdRt741Dz-c5YWNy3x\
                                    Yk5Nr8r-2tLIAnL1-Go0GSjnXEgn03wuoIpeMskVirS5YPmjzxR3RZpw_tSeFNzE95ahELBMCE4RbuD6hor8FdrV4O3Y1It3GttN0J\
                                        SAymipYfkWlK-enpRysqdUp_axUwNQtUCLnha9TvFDWAtsT1Jh4Q27BA-uXiR9ng5dDzjrnJ0JDtXiAkyLGo7hiFo3h_C1Qb1a6ZBSNbm\
                                            YZaIHYNzY49Abk2QDr4gY7yovBaaRxKPl6to8BCs5lzRfqb3cH1Vjk-BkdfuGPhXpqiyZ65wnkiAtXi-MsZKQC2qVnoAJcLqR9EFv_Kz\
                                                sjq_AqGDOCqx2WT1dsLLWIQVf5y1cchZkYZ2d-B-dxYHhV2G8NKlwgYHCy2XFsP-99n1CGxs28Qli6-s-Un3tozyWovn7GKRcjFjJbXR\
                                                    efF9hUVp867F9Hz6uBmUYF_HV_RsmFM2ii4s6pdTW5lnbcQsS9oEnGyeES'

def upload_file_to_dropbox(file_path, dropbox_path):
    #Initialize Dropbox client
    dbx = dropbox.Dropbox(ACCESS_TOKEN)

    try:
        #Open the file and upload it
        with open(file_path, 'rb') as f:
            dbx.files_upload(f.read(), dropbox_path, mode=dropbox.files.WriteMode.overwrite)
            print(f"File {file_path} uploaded to Dropbox as {dropbox_path}")
    except dropbox.exceptions.ApiError as err:
        print(f"API error: {err}")
    except FileNotFoundError:
        print(f"Error: The file {file_path} was not found.")
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

#Main function
if __name__ == "__main__":
    while True:
        print("\n1. Upload a file to Dropbox")
        print("2. Search and download a file from Dropbox")
        print("3. Exit")
        choice = input("Enter your choice (1/2/3): ")

        if choice == "1":
            # Upload a file
            file_path = input("Enter the path to the file you want to upload: ")
            dropbox_path = input("Enter the Dropbox path (e.g., /folder/filename.txt): ")
            upload_file_to_dropbox(file_path, dropbox_path)
        elif choice == "2":
            # Search and download a file
            file_name = input("Enter the file name (without extension) to search and download: ")
            search_and_download_file(file_name)
        elif choice == "3":
            print("Exiting...")
            break
        else:
            print("Invalid choice. Please try again.")
