import os
import numpy as np
from pdf2image import convert_from_bytes
from PIL import Image
from time import time
from segmentation.extract_text import extract_text

def segment_pdf(pdfs : list[tuple],  
                target_segment_directory : str = None, 
                expand:  bool = True, 
                visualization : bool = False,
                get_text : bool = False
                ) -> tuple[
                    list[tuple[str, int, bytes]], 
                    list[str] 
                    ]:
    """
    Segment chemical structures from PDF pages using the decimer_segmentation library.

    Parameters:
        pdfs (list[tuple]): A list of tuples containing the PDF filename and its content in bytes.
        directory (str): The path to the directory where the segmented images should be saved.
        expand (bool): If True, decimer_segmentation expands the masks generated by the model, for most purposes this is better.
        visualization (bool): If True, displays the segmentation for visual confirmation.

    Returns:
        list[tuple]: A list of tuples containing the filename and segmented images extracted from the PDF.
    """
    print("Importing decimer segmentation...")
    import_start = time()
    from decimer_segmentation import segment_chemical_structures
    print(f"Importing decimer took: {time() - import_start} s")

    print("Segmenting...")
    segmentation_start = time()
    
    # prep saving directory
    if target_segment_directory:
        os.makedirs(target_segment_directory, exist_ok=True)

    # segmentation
    segment_list = []
    text_list = []
    for (filename, content) in pdfs:

        # process pdfs
        try:
            pages = convert_from_bytes(content, 300)
        except Exception as e:
            print(f"Error while processing {filename}: {str(e)}")
            continue

        # call the segmentation function
        # visualization can be set to True for a visual confirmation of the segmentation
        # expand=True yields better results than expand=False
        sub_segment_list = []
        print(f"Attempting to segment {filename}")
        for page_num, page in enumerate(pages):
            segments, bboxes = segment_chemical_structures(np.array(page),
                                                   expand=expand,
                                                   visualization=visualization)
            for index, segment in enumerate(segments):
                image = Image.fromarray(segment)
                sub_segment_list.append((filename, page_num, image))
            if get_text:
                text_list += (extract_text(os.path.join('pdf_extraction/pdfs', filename), page_num, bboxes))



        print(f"Found {len(sub_segment_list)} segments in {filename}")

        # save to specified directory
        if target_segment_directory:
            os.makedirs(os.path.join(target_segment_directory, filename), exist_ok=True)
            for index, (filename, segment) in enumerate(sub_segment_list):
                segment.save(os.path.join(target_segment_directory, f"{filename}/{index}.png"))
            print(f"Segments from {filename} saved into {target_segment_directory}/{filename}")
        segment_list += sub_segment_list


    print(f"{len(segment_list)} segments were segmented.\nSegmentation took {time() - segmentation_start} s\n({(time() - segmentation_start)/len(segment_list)} s per segment)")
    return segment_list, text_list

def main(): 
    # example use:
    filepath = "pdf_extraction/pdfs/DH-MOTM-Poster-June-2023-Revised.pdf"
    with open(filepath, "rb") as f:
        _, text = segment_pdf([("DH-MOTM-Poster-June-2023-Revised.pdf", f.read())], target_segment_directory="segmentation/segments/experiments", expand=True)
        print("\n->".join(text))

if __name__ == '__main__':
    main()
