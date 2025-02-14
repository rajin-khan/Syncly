import dropbox

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

if __name__ == "__main__":
    #Take file path as user input
    file_path = input("Enter the path to the file you want to upload: ")
    
    #Define the Dropbox path where the file will be uploaded (We'll update it with user input next time)
    dropbox_path = f'/{file_path.split("/")[-1]}'  #Uploads with the same filename

    #Call the function to upload the file
    upload_file_to_dropbox(file_path, dropbox_path)
    