from argparse import ArgumentParser
from calendar import month_name

from export.export_results import export_to_csv
from export.remove_duplicates import remove_duplicates
from pdf_extraction.pdf_extraction import download_pdf
from recognition.recognize_segments_decimer import \
    recognize_segments as recognize_segments_decimer
from recognition.recognize_segments_molscribe import \
    recognize_segments as recognize_segments_molscribe
from segmentation.segment_pdf import segment_pdf
from validation.validate_with_chembl_webresource import validate_inchikey_list


def get_information_from_descriptions(descriptions : list[str], separator : str) -> dict:
    """
    Attempt to parse information out of a list of descriptions.

    The first line of drughunter descriptions often contains a '|' character
    that splits the line into NAME and TARGET
    If it does not contain the '|' character, it is common that the NAME is contained
    within the first line and TARGET within the second line
    
    In: 
        - descriptions -> list of individual descriptions, commonly they contain lines separated by '\n'
    Out:
        - dict with keys ['description', 'proposed_name', 'proposed_target'] that points towards equally long lists

    TODO?:
    Occassionally the text extraction module puts the name and target on last two lines
    It could be possible to handle that to increase correct name, target proposal rate
    """

    proposed_names, porposed_targets = [], []
    for description in descriptions:
        proposed_name, porposed_target = '', ''
        text_lines = description.split('\n')
        for text_line in text_lines:
            if separator in text_line:
                proposed_name, porposed_target = text_line.split(separator)
                break

        if proposed_name == '':
            if len(text_lines) >= 1:
                proposed_name = text_lines[0]
            if len(text_lines) >= 2:
                porposed_target = text_lines[1]
                
        proposed_names.append(proposed_name)
        porposed_targets.append(porposed_target)

    information = {
        'description': descriptions,
        'proposed_name': proposed_names,
        'proposed_target': porposed_targets
    }
    return information


def extract_molecules_from_pdfs(pdfs : list[tuple[str, bytes]], 
                                target_segment_directory : str = None, 
                                decimer_complement : bool = True,
                                get_text : bool = False,
                                text_direction : str = 'right',
                                molecules_of_the_month : bool = True,
                                separator : str = '|'
                                ) -> None:
    """
    Extract molecules from a list of PDFs 

    Parameters:
    - pdfs (List[Tuple[str, bytes]]): A list of tuples containing the source file name and the content of the PDF.
      Each tuple represents one PDF to be processed.
    - target_segment_directory (str): Path to the directory that segments segmented with decimer are saved to

    Returns:
    - Nothing, instead saves the results into a timestamped csv file
    - prints rates of successful and unsuccessful recognitions using Molscribe and Decimer.
    """

    extraction_results = {}

    # segmentation_results -> list of tuples (source filename, segment)
    segmentation_results, descriptions = segment_pdf(pdfs, target_segment_directory=target_segment_directory, get_text=get_text, molecules_of_the_month=molecules_of_the_month, text_direction=text_direction) 

    # get get results of segmentation
    extraction_results = {
        'source': [source_filename for source_filename, _, _, _ in segmentation_results],
        'page number': [page_number for _, page_number, _, _ in segmentation_results],
        'segment number': [segment_number for _, _, segment_number, _ in segmentation_results]
    }

    segments = [segment for _, _, _, segment in segmentation_results]
    if (descriptions):
        extraction_results.update(get_information_from_descriptions(descriptions, separator))

    
    # recognize with Molscribe
    recognition_results_molscribe = recognize_segments_molscribe(segments)

    # validate results with unichem
    recognition_results_molscribe['validation'] = validate_inchikey_list(recognition_results_molscribe.get('inchikey'))

    # print rates
    if recognition_results_molscribe['validation']:
        print(f"Molscribe succesfully recognized {recognition_results_molscribe['validation'].count(True)} segments. \
            ({round(recognition_results_molscribe['validation'].count(True)/len(recognition_results_molscribe['validation'])*100, 2)} % success rate)")
        print(f"Molscribe could not recognize {recognition_results_molscribe['validation'].count(False)} segments. Attemping to recognize them with decimer.")
   
    if decimer_complement:
        # get indexes of invalidated segments
        index_list = [index for index, validation_result in enumerate(recognition_results_molscribe['validation']) if validation_result is False]

        # recognize with decimer
        if index_list:
            recognition_results_decimer = recognize_segments_decimer([segment for index, segment in enumerate(segments) if index in index_list ])


            # validate results with unichem
            recognition_results_decimer['validation'] = validate_inchikey_list(recognition_results_decimer.get('inchikey'))
            
            print(f"Decimer managed to recognize {recognition_results_decimer['validation'].count(True)} more segments.")

            # complement molscribe unsuccessful recognitions with successful decimer recognitions
            for index, validation_result in enumerate(recognition_results_decimer['validation']):
                # if decimer got better result that molscribe
                if validation_result is True or (recognition_results_decimer['inchikey'] != '' and recognition_results_molscribe['inchikey'] == ''):
                    for key in ['smiles', 'inchi', 'inchikey', 'validation']:
                        recognition_results_molscribe[key][index_list[index]] = recognition_results_decimer[key][index]

    # update and remove duplicates
    extraction_results.update(recognition_results_molscribe)
    extraction_results = remove_duplicates(extraction_results)

    # print rates
    if extraction_results['validation']:
        print(f"{extraction_results['validation'].count(True)} segments recognized in total. \
            ({round(extraction_results['validation'].count(True)/len(extraction_results['validation'])*100, 2)} % success rate)")
    
    if extraction_results:
        export_to_csv(extraction_results)
    else:
        print("Nothing was extracted.")


def extract_molecules_of_the_month(target_year : int, 
                                   target_months : tuple[int, int], 
                                   target_segment_directory : str = None, 
                                   decimer_complement : bool = True,
                                   get_text : bool = False
                                   ) -> None:
    """
    Extract from the Molecules of the Month DrugHunter sets for specified year and month range

    Params:
    - target_year (int): Year to extract molecules of the month.
    - target_months (str): Range of months, format either single number ('5'), or two numbers separated by a dash ('1-3')
    - target_segment_directory (str): Directory to save segmented pngs to

    Returns:
    - see documentation of extract_molecules_from_pdf
    """

    # get list of target urls
    urls = [f"https://drughunter.com/molecules-of-the-month/{target_year}/{month_name[index].lower()}-{target_year}" for index in range(target_months[0], target_months[1] + 1)]
    
    # get pdfs to extract from
    pdfs = []
    for url in urls:
        pdfs += download_pdf(url, download_all=True) 
    

    # get chemical info out of pdfs
    if pdfs:
        extract_molecules_from_pdfs(pdfs, target_segment_directory=target_segment_directory, decimer_complement=decimer_complement, get_text=get_text, text_direction='right')


def extract_bounds(input_string : str) -> tuple[int, int]:
    """
    Extract lower and upper bounds out of a string

    Params:
    - input_string: Range of months, format either single number ('5'), or two numbers separated by a dash ('1-3')

    Returns:
    - lower_bound: The earliest month in the string
    - upper_bound: The latest month in the string
    """

    # if the string is just one number
    try:
        if (int(input_string) >= 1 and int(input_string) <= 12):
            lower_bound, upper_bound = int(input_string), int(input_string)
            return lower_bound, upper_bound
        else:
            raise ValueError("Invalid input format or out-of-range values.")
    
    # if the string is two numbers separated by a dash
    except:
        try:
            lower_bound, upper_bound = map(int, input_string.split('-'))
            if 1 <= lower_bound <= 12 and 1 <= upper_bound <= 12 and lower_bound < upper_bound:
                return lower_bound, upper_bound
            else:
                raise ValueError("Invalid input format or out-of-range values.")
        except (ValueError, IndexError):
            raise ValueError("Invalid input format. Please enter two numbers separated by a dash in the range of 1 to 12, with the first being smaller than the latter. Or a single number")


def main():
    """
    Main function to handle command-line arguments and execute the appropriate extraction based on the arguments.
    
    see -h, --help for documentation
    """
    parser = ArgumentParser(description='DrugHunter extractor')
    parser.add_argument('-y', '--year', type=int, help='(int) targeted year of drughunter molecules of the month set')
    parser.add_argument('-m', '--month', type=str, help='(str) targeted month range of the molecules of the month set, input either two numbers separated by a dash or a single number (borders of the range are included)')
    parser.add_argument('-u', '--url', type=str, help='(str) url of webpage with targeted set (in case the format of drughunter url changes, which is likely)')
    parser.add_argument('--seg_dir', type=str, help='(str) directory that the segmented segments will be saved into, if unspecified, segments will not be saved', default=None)
    parser.add_argument('--decimer_off', help='Turns off decimer complementation', action='store_true')
    parser.add_argument('--text', help='Turns on text extraction', action='store_true')
    parser.add_argument('--direction', type=str, help='Specifies in which direction the text is from the molecules', default='right')
    parser.add_argument('--separator', type=str, help='Specifies which separator is used in the document to separate name and target.', default='|')
    args = parser.parse_args()

    
    decimer_on = not args.decimer_off

    if args.url and args.year:
        print("Please use only one option.")

    # user requested a specific url to be checked, year and set is ignored
    if args.url:
        extract_molecules_from_pdfs(
            download_pdf(args.url, download_all=False), 
            target_segment_directory=args.seg_dir, 
            decimer_complement=decimer_on, 
            get_text=args.text,
            text_direction=args.direction,
            molecules_of_the_month = False,
            separator = args.separator
            )
        return
    
    # user has not picked the year
    if not args.year:
        print("No year or url provided")
        return

    if len(str(args.year)) != 4:
        print("Invalid year format. Please provide a 4-digit year (YYYY).")
        return

    if (args.year < 2020):
        print("DrugHunter molecules of the month start at the year 2020, please provide a year equal or greater.")
        return
    
    if args.month:
        lower_bound, upper_bound = extract_bounds(args.month)
    else:
        lower_bound, upper_bound = 1, 12
    
    extract_molecules_of_the_month(
        args.year, (lower_bound, upper_bound), 
        args.seg_dir, 
        decimer_complement=decimer_on, 
        get_text=args.text)
    return

if __name__ == "__main__":
    main()