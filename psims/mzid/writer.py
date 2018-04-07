import warnings
from numbers import Number

try:
    from collections import Mapping
except ImportError:
    from collections.abc import Mapping

from .components import (
    MzIdentML,
    ComponentDispatcher, etree, common_units, element, _element,
    default_cv_list, CVParam, UserParam,
    _xmlns, AUTO, DEFAULT_ORGANIZATION_ID, DEFAULT_CONTACT_ID)

from psims.xml import XMLWriterMixin, XMLDocumentWriter

from .utils import ensure_iterable

_t = tuple()


class DocumentSection(ComponentDispatcher, XMLWriterMixin):

    def __init__(self, section, writer, parent_context, section_args=None, **kwargs):
        if section_args is None:
            section_args = dict()
        section_args.update(kwargs)
        super(DocumentSection, self).__init__(parent_context)
        self.section = section
        self.writer = writer
        self.section_args = section_args
        self.params = section_args.pop("params", [])
        self.params = self.prepare_params(self.params)
        self.toplevel = None
        self._context_manager = None

    def _create_element(self):
        if self.toplevel is None:
            el = _element(self.section, **self.section_args)
            if 'id' in self.section_args:
                self.context[self.section][el.id] = self.section_args['id']
            self.toplevel = el

    def __enter__(self):
        self._create_element()
        with_id = 'id' in self.section_args
        self._context_manager = self.toplevel.begin(self.writer, with_id=with_id)
        self._context_manager.__enter__()
        for param in self.params:
            param(self.writer)

    def __exit__(self, exc_type, exc_value, traceback):
        self._context_manager.__exit__(exc_type, exc_value, traceback)
        self.writer.flush()


class InputsSection(DocumentSection):
    def __init__(self, writer, parent_context, section_args=None, **kwargs):
        super(InputsSection, self).__init__(
            "Inputs", writer, parent_context,
            xmlns=_xmlns)


class AnalysisProtocolCollectionSection(DocumentSection):
    def __init__(self, writer, parent_context, section_args=None, **kwargs):
        super(AnalysisProtocolCollectionSection, self).__init__(
            "AnalysisProtocolCollection", writer, parent_context,
            xmlns=_xmlns)


class AnalysisSampleCollectionSection(DocumentSection):
    def __init__(self, writer, parent_context, section_args=None, **kwargs):
        super(AnalysisSampleCollectionSection, self).__init__(
            "AnalysisSampleCollection", writer, parent_context,
            xmlns=_xmlns)


class SequenceCollectionSection(DocumentSection):
    def __init__(self, writer, parent_context, section_args=None, **kwargs):
        super(SequenceCollectionSection, self).__init__(
            "SequenceCollection", writer, parent_context, xmlns=_xmlns)


class AnalysisCollectionSection(DocumentSection):
    def __init__(self, writer, parent_context, section_args=None, **kwargs):
        super(AnalysisCollectionSection, self).__init__(
            "AnalysisCollection", writer, parent_context, xmlns=_xmlns)


class DataCollectionSection(DocumentSection):
    def __init__(self, writer, parent_context, section_args=None, **kwargs):
        super(DataCollectionSection, self).__init__(
            "DataCollection", writer, parent_context, xmlns=_xmlns)


class AnalysisDataSection(DocumentSection):
    def __init__(self, writer, parent_context, section_args=None, **kwargs):
        super(AnalysisDataSection, self).__init__(
            "AnalysisData", writer, parent_context, xmlns=_xmlns)


class SpectrumIdentficationListSection(DocumentSection):
    def __init__(self, writer, parent_context, section_args=None, **kwargs):
        super(SpectrumIdentficationListSection, self).__init__(
            "SpectrumIdentificationList",
            writer, parent_context, section_args=section_args, **kwargs)
        self.fragmentation_table = self.section_args.pop('fragmentation_table', None)

    def __enter__(self):
        super(SpectrumIdentficationListSection, self).__enter__()
        if self.fragmentation_table:
            self.fragmentation_table.write(self.writer)

class ProteinDetectionListSection(DocumentSection):
    def __init__(self, writer, parent_context, section_args=None, **kwargs):
        super(ProteinDetectionListSection, self).__init__(
            "ProteinDetectionList", writer, parent_context, section_args=section_args, **kwargs)
        count = self.section_args.pop('count', None)
        has_count_param = any(param.accession == 'MS:1002404' for param in self.params)
        if count is None and not has_count_param:
            warnings.warn("MS:1002404 \"count of identified proteins\" is missing."
                "Provide it as either a section parameter or as the \"count\" keyword argument")
        if count is not None and has_count_param:
            raise ValueError("MS:1002404 \"count of identified proteins\" was supplied both "
                             "as a parameter and as a keyword argument.")
        if count is not None:
            self.params.append(self.param(name="count of identified proteins", value=int(count)))



# ----------------------
# Order of Instantiation
# Providence -> Input -> Protocol -> Identification


class MzIdentMLWriter(ComponentDispatcher, XMLDocumentWriter):
    """
    A high level API for generating MzIdentML XML files from simple Python objects.

    This class depends heavily on lxml's incremental file writing API which in turn
    depends heavily on context managers. Almost all logic is handled inside a context
    manager and in the context of a particular document. Since all operations assume
    that they have access to a universal identity map for each element in the document,
    that map is centralized in this instance.

    MzIdentMLWriter inherits from :class:`.ComponentDispatcher`, giving it a :attr:`context`
    attribute and access to all `Component` objects pre-bound to that context with attribute-access
    notation.

    Attributes
    ----------
    outfile : file
        The open, writable file descriptor which XML will be written to.
    xmlfile : lxml.etree.xmlfile
        The incremental XML file wrapper which organizes file writes onto :attr:`outfile`.
        Kept to control context.
    writer : lxml.etree._IncrementalFileWriter
        The incremental XML writer produced by :attr:`xmlfile`. Kept to control context.
    toplevel : lxml.etree._FileWriterElement
        The top level incremental xml writer element which will be closed at the end
        of file generation. Kept to control context
    context : :class:`.DocumentContext`
    """

    toplevel_tag = MzIdentML

    def __init__(self, outfile, vocabularies=None, **kwargs):
        if vocabularies is None:
            vocabularies = list(default_cv_list)
        ComponentDispatcher.__init__(self, vocabularies=vocabularies)
        XMLDocumentWriter.__init__(self, outfile, **kwargs)

    def controlled_vocabularies(self, vocabularies=None):
        if vocabularies is None:
            vocabularies = []
        self.vocabularies.extend(vocabularies)
        cvlist = self.CVList(self.vocabularies)
        cvlist.write(self.writer)

    def providence(self, software=tuple(), owner=tuple(), organization=tuple(), provider=None):
        """
        Write the analysis providence section, a top-level segment of the MzIdentML document

        This section should be written early on to register the list of software used in this
        analysis

        Parameters
        ----------
        software : dict or list of dict, optional
            A single dictionary or list of dictionaries specifying an :class:`AnalysisSoftware` instance
        owner : dict, optional
            A dictionary specifying a :class:`Person` instance. If missing, a default person will be created
        organization : dict, optional
            A dictionary specifying a :class:`Organization` instance. If missing, a default organization will
            be created
        """
        organization = [self.Organization.ensure(o or {}) for o in ensure_iterable(organization)]
        owner = [self.Person.ensure(o or {}) for o in ensure_iterable(owner)]
        software = [self.AnalysisSoftware.ensure(s or {})
                    for s in ensure_iterable(software)]

        if not owner and not organization:
            affiliation = DEFAULT_ORGANIZATION_ID
            self.register("Organization", affiliation)
            owner = [self.Person(affiliation=affiliation)]
            organization = [self.Organization(id=affiliation)]

        self.GenericCollection("AnalysisSoftwareList",
                               software).write(self.writer)
        if owner:
            owner_id = owner[0].id
        else:
            owner_id = None
        self.Provider(contact=owner_id).write(self.writer)
        self.AuditCollection(owner, organization).write(self.writer)

    def inputs(self, source_files=tuple(), search_databases=tuple(), spectra_data=tuple()):
        source_files = [self.SourceFile.ensure(s or {})
                        for s in ensure_iterable(source_files)]
        search_databases = [self.SearchDatabase.ensure(
            s or {}) for s in ensure_iterable(search_databases)]
        spectra_data = [self.SpectraData.ensure(s or {})
                        for s in ensure_iterable(spectra_data)]

        self.Inputs(source_files, search_databases,
                    spectra_data).write(self.writer)

    def analysis_protocol_collection(self):
        return AnalysisProtocolCollectionSection(self.writer, self.context)

    def sequence_collection(self):
        return SequenceCollectionSection(self.writer, self.context)

    def analysis_collection(self):
        return AnalysisCollectionSection(self.writer, self.context)

    def data_collection(self):
        return DataCollectionSection(self.writer, self.context)

    def _sequence_collection(self, db_sequences=tuple(), peptides=tuple(), peptide_evidence=tuple()):
        db_sequences = (self.DBSequence.ensure((s or {}))
                        for s in ensure_iterable(db_sequences))
        peptides = (self.Peptide.ensure((s or {}))
                    for s in ensure_iterable(peptides))
        peptide_evidence = (self.PeptideEvidence.ensure((s or {}))
                            for s in ensure_iterable(peptide_evidence))

        self.SequenceCollection(db_sequences, peptides,
                                peptide_evidence).write(self.writer)

    def write_db_sequence(self, accession, sequence=None, id=None, search_database_id=1, params=None, **kwargs):
        el = self.DBSequence(
            accession=accession, sequence=sequence, id=id,
            search_database_id=search_database_id, params=params, **kwargs)
        el.write(self.writer)

    def write_peptide(self, peptide_sequence, id, modifications=None, params=None, **kwargs):
        el = self.Peptide(
            peptide_sequence=peptide_sequence, id=id, modifications=modifications,
            params=params, **kwargs)
        el.write(self.writer)

    def write_peptide_evidence(self, peptide_id, db_sequence_id, id, start_position, end_position,
                               is_decoy=False, pre=None, post=None, params=None, frame=None, translatio_table_id=None,
                               **kwargs):
        el = self.PeptideEvidence(
            peptide_id=peptide_id, db_sequence_id=db_sequence_id, id=id,
            start_position=start_position, end_position=end_position, is_decoy=is_decoy,
            pre=pre, post=post, frame=frame, translatio_table_id=translatio_table_id,
            params=params, **kwargs)
        el.write(self.writer)

    def spectrum_identification_protocol(self, search_type='ms-ms search', analysis_software_id=1, id=1,
                                         additional_search_params=None, enzymes=None, modification_params=None,
                                         fragment_tolerance=None, parent_tolerance=None, threshold=None):
        enzymes = [self.Enzyme.ensure((s or {})) for s in ensure_iterable(enzymes)]
        modification_params = [self.SearchModification.ensure(
            (s or {})) for s in ensure_iterable(modification_params)]
        if isinstance(fragment_tolerance, (list, tuple)):
            fragment_tolerance = self.FragmentTolerance(*fragment_tolerance)
        elif isinstance(fragment_tolerance, Number):
            if fragment_tolerance < 1e-4:
                fragment_tolerance = self.FragmentTolerance(fragment_tolerance * 1e6, None, "parts per million")
            else:
                fragment_tolerance = self.FragmentTolerance(fragment_tolerance, None, "dalton")

        if isinstance(parent_tolerance, (list, tuple)):
            parent_tolerance = self.ParentTolerance(*parent_tolerance)
        elif isinstance(parent_tolerance, Number):
            if parent_tolerance < 1e-4:
                parent_tolerance = self.ParentTolerance(parent_tolerance * 1e6, None, "parts per million")
            else:
                parent_tolerance = self.ParentTolerance(parent_tolerance, None, "dalton")
        threshold = self.Threshold(threshold)
        protocol = self.SpectrumIdentificationProtocol(
            search_type, analysis_software_id, id, additional_search_params,
            modification_params, enzymes, fragment_tolerance,
            parent_tolerance, threshold)
        protocol.write(self.writer)

    def protein_detection_protocol(self, threshold=None, analysis_software_id=1, id=1, params=None, **kwargs):
        protocol = self.ProteinDetectionProtocol(
            id=id,
            threshold=threshold, params=params, analysis_software_id=analysis_software_id,
            **kwargs)
        protocol.write(self.writer)

    def analysis_data(self):
        return AnalysisDataSection(self.writer, self.context)

    def _spectrum_identification_list(self, id, identification_results=None, measures=None):
        if measures is None:
            measures = self.FragmentationTable()
        converting = (self.spectrum_identification_result(**(s or {}))
                      for s in ensure_iterable(identification_results))
        self.SpectrumIdentificationList(
            id=id, identification_results=converting,
            fragmentation_table=measures).write(self.writer)

    def spectrum_identification_list(self, id, measures=None):
        if measures is None:
            measures = self.FragmentationTable()
        return SpectrumIdentficationListSection(self.writer, self.context, id=id, fragmentation_table=measures)

    def write_spectrum_identification_result(self, spectrum_id, id, spectra_data_id=1,
                                             identifications=None, params=None, **kwargs):
        el = self.SpectrumIdentificationResult(
            spectra_data_id=spectra_data_id,
            spectrum_id=spectrum_id,
            id=id,
            params=params,
            identifications=(self.spectrum_identification_item(**(s or {}))
                             if isinstance(s, Mapping) else self.SpectrumIdentificationItem.ensure(s)
                             for s in ensure_iterable(identifications)), **kwargs)
        el.write(self.writer)

    def spectrum_identification_result(self, spectrum_id, id, spectra_data_id=1, identifications=None,
                                       params=None, **kwargs):
        return self.SpectrumIdentificationResult(
            spectra_data_id=spectra_data_id,
            spectrum_id=spectrum_id,
            id=id,
            params=params,
            identifications=(self.spectrum_identification_item(**(s or {}))
                             if isinstance(s, Mapping) else self.SpectrumIdentificationItem.ensure(s)
                             for s in ensure_iterable(identifications)), **kwargs)

    def spectrum_identification_item(self, experimental_mass_to_charge,
                                     charge_state, peptide_id, peptide_evidence_id, score, id,
                                     calculated_mass_to_charge=None, calculated_pi=None,
                                     ion_types=None, params=None, pass_threshold=True, rank=1,
                                     **kwargs):
        return self.SpectrumIdentificationItem(
            experimental_mass_to_charge=experimental_mass_to_charge,
            charge_state=charge_state, peptide_id=peptide_id,
            peptide_evidence_ids=peptide_evidence_id, score=score, id=id,
            ion_types=ion_types, calculated_mass_to_charge=calculated_mass_to_charge,
            params=ensure_iterable(params), pass_threshold=pass_threshold, rank=rank,
            **kwargs)

    def protein_detection_list(self, id, count=None, params=None, **kwargs):
        return ProteinDetectionListSection(
            self.writer, self.context, id=id, count=count, params=params, **kwargs)


    def write_protein_ambiguity_group(self, protein_detection_hypotheses, id, pass_threshold=True,
                                      params=None, **kwargs):
        group = self.protein_ambiguity_group(
            protein_detection_hypotheses=protein_detection_hypotheses, id=id,
            pass_threshold=pass_threshold, params=params, **kwargs)
        group.write(self.writer)

    def protein_ambiguity_group(self, protein_detection_hypotheses, id, pass_threshold=True,
                                params=None, **kwargs):
        converting = (self.protein_detection_hypothesis(**(s or {}))
                      if isinstance(s, Mapping) else self.ProteinDetectionHypothesis.ensure(s)
                      for s in ensure_iterable(protein_detection_hypotheses))
        el = self.ProteinAmbiguityGroup(
            id=id, protein_detection_hypotheses=converting, pass_threshold=pass_threshold,
            params=params, **kwargs)
        return el

    def protein_detection_hypothesis(self, db_sequence_id, id, peptide_hypotheses,
                                     pass_threshold=True, name=None, params=None, **kwargs):
        converting = (self.peptide_hypothesis(**(s or {}))
                      if isinstance(s, Mapping) else self.PeptideHypothesis.ensure(s)
                      for s in ensure_iterable(peptide_hypotheses))
        el = self.ProteinDetectionHypothesis(
            id=id, db_sequence_id=db_sequence_id, peptide_hypotheses=converting,
            pass_threshold=pass_threshold, name=name, params=params, **kwargs)
        return el

    def peptide_hypothesis(self, peptide_evidence_id, spectrum_identification_ids, params=None,
                           **kwargs):
        el = self.PeptideHypothesis(
            peptide_evidence_id, spectrum_identification_ids, params=params, **kwargs)
        return el
