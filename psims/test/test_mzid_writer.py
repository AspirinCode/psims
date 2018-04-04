from psims.mzid import MzIdentMLWriter
from pyteomics import mzid
from lxml import etree

from psims.test import mzid_data
from psims.test.utils import output_path as output_path


def test_write(output_path):
    software = mzid_data.software
    spectra_data = mzid_data.spectra_data
    search_database = mzid_data.search_database
    spectrum_identification_list = mzid_data.spectrum_identification_list

    proteins = mzid_data.proteins
    peptides = mzid_data.peptides
    peptide_evidence = mzid_data.peptide_evidence

    protocol = mzid_data.protocol
    analysis = mzid_data.analysis
    source_file = mzid_data.source_file

    f = MzIdentMLWriter(open(output_path, 'wb'))
    with f:
        f.controlled_vocabularies()
        f.providence(software=software)
        f.register("SpectraData", spectra_data['id'])
        f.register("SearchDatabase", search_database['id'])
        f.register("SpectrumIdentificationList", spectrum_identification_list["id"])
        f.register("SpectrumIdentificationProtocol", protocol['id'])

        with f.sequence_collection():
            for prot in proteins:
                f.write_db_sequence(**prot)
            for pep in peptides:
                f.write_peptide(**pep)
            for evid in peptide_evidence:
                f.write_peptide_evidence(**evid)

        with f.analysis_collection():
            f.SpectrumIdentification(*analysis).write(f)
        with f.analysis_protocol_collection():
            f.spectrum_identification_protocol(**protocol)
        with f.data_collection():
            f.inputs(source_file, search_database, spectra_data)
            with f.analysis_data():
                with f.spectrum_identification_list(id=spectrum_identification_list['id']):
                    for result in spectrum_identification_list['identification_results']:
                        f.write_spectrum_identification_result(**result)

    try:
        f.format()
        f.close()
    except OSError:
        pass

    reader = mzid.read(output_path)
    n_peptide_evidence = len(peptide_evidence)
    assert n_peptide_evidence == len(list(reader.iterfind("PeptideEvidence")))
    n_spectrum_identification_results = len(spectrum_identification_list['identification_results'])
    reader.reset()
    assert n_spectrum_identification_results == len(list(reader.iterfind("SpectrumIdentificationResult")))
    reader.reset()
    protocol = next(reader.iterfind("SpectrumIdentificationProtocol"))
    mods = protocol['ModificationParams']['SearchModification']
    assert len(mods) == 2
    assert mods[0]['fixedMod']
    assert not mods[1]['fixedMod']
    assert "unknown modification" in mods[1]
    reader.close()
