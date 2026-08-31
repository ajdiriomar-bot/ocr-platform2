import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import * as XLSX from 'xlsx';
import api from '../api';
import NotificationBell from '../components/NotificationBell';

const MISSING = 'Non détecté';
const MISSING_DATE = 'Non détectée';

const EMPTY_STRUCTURED_DATA = {
  provider: MISSING,
  client: MISSING,
  date: MISSING_DATE,
  invoice_number: MISSING,
  ice: MISSING,
  client_ice: MISSING,
  rc: MISSING,
  if_number: MISSING,
  cnss: MISSING,
  tva_percentage: MISSING,
  tva: MISSING,
  total_ht: MISSING,
  total_ttc: MISSING,
  calculated_fields: [],
  calculation_details: [],
  warnings: [],
};

const EMPTY_ICE_VERIFICATION = {
  status: 'non_verifie',
  company_name: null,
  message: "L'ICE n'a pas encore été vérifié.",
  verification_url: null,
};

const normalizeInvoiceData = (data = {}) => ({
  provider: data.provider || MISSING,
  client: data.client || MISSING,
  date: data.date || data.invoice_date || MISSING_DATE,
  invoice_number: data.invoice_number || MISSING,
  ice: data.supplier_ice || data.ice || MISSING,
  client_ice: data.client_ice || MISSING,
  rc: data.rc || MISSING,
  if_number: data.if_number || MISSING,
  cnss: data.cnss || MISSING,
  tva_percentage: data.tva_percentage || MISSING,
  tva: data.tva || MISSING,
  total_ht: data.total_ht || MISSING,
  total_ttc: data.total_ttc || MISSING,
  calculated_fields: Array.isArray(data.calculated_fields)
    ? data.calculated_fields
    : [],
  calculation_details: Array.isArray(data.calculation_details)
    ? data.calculation_details
    : [],
  warnings: Array.isArray(data.warnings) ? data.warnings : [],
});

const normalizeIceVerification = (data = {}) => ({
  status:
    data.status ??
    data.ice_verification_status ??
    EMPTY_ICE_VERIFICATION.status,
  company_name:
    data.company_name ??
    data.verified_company_name ??
    EMPTY_ICE_VERIFICATION.company_name,
  message:
    data.message ??
    data.ice_verification_message ??
    EMPTY_ICE_VERIFICATION.message,
  verification_url:
    data.verification_url ??
    data.ice_verification_url ??
    EMPTY_ICE_VERIFICATION.verification_url,
});

const getIceVerificationPresentation = (status) => {
  switch (status) {
    case 'valide_mathematiquement':
      return {
        label: 'Structure ICE valide',
        icon: '✅',
        containerClass: 'bg-green-50 border-green-200 text-green-800',
        badgeClass: 'bg-green-100 text-green-700 border-green-200',
      };

    case 'cle_invalide':
      return {
        label: 'Clé ICE invalide',
        icon: '❌',
        containerClass: 'bg-red-50 border-red-200 text-red-800',
        badgeClass: 'bg-red-100 text-red-700 border-red-200',
      };

    case 'format_invalide':
      return {
        label: 'Format ICE invalide',
        icon: '❌',
        containerClass: 'bg-red-50 border-red-200 text-red-800',
        badgeClass: 'bg-red-100 text-red-700 border-red-200',
      };

    case 'non_detecte':
      return {
        label: 'ICE non détecté',
        icon: '⚠️',
        containerClass: 'bg-amber-50 border-amber-200 text-amber-800',
        badgeClass: 'bg-amber-100 text-amber-700 border-amber-200',
      };

    case 'service_indisponible':
      return {
        label: 'Service indisponible',
        icon: '⚠️',
        containerClass: 'bg-orange-50 border-orange-200 text-orange-800',
        badgeClass: 'bg-orange-100 text-orange-700 border-orange-200',
      };

    default:
      return {
        label: 'ICE non vérifié',
        icon: '⏳',
        containerClass: 'bg-gray-50 border-gray-200 text-gray-700',
        badgeClass: 'bg-gray-100 text-gray-600 border-gray-200',
      };
  }
};

const isSupportedFile = (file) =>
  file?.type?.startsWith('image/') || file?.type === 'application/pdf';

const getApiErrorMessage = (
  error,
  fallback = 'Une erreur est survenue.',
) => {
  const detail = error?.response?.data?.detail;

  if (!detail) {
    return error?.message || fallback;
  }

  if (typeof detail === 'string') {
    return detail;
  }

  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === 'string') {
          return item;
        }

        if (item?.msg) {
          const location = Array.isArray(item.loc)
            ? item.loc.join(' → ')
            : '';

          return location ? `${location} : ${item.msg}` : item.msg;
        }

        return JSON.stringify(item);
      })
      .join(' | ');
  }

  if (typeof detail === 'object') {
    return detail.message || JSON.stringify(detail);
  }

  return fallback;
};

const documentToStructuredData = (document = {}) =>
  normalizeInvoiceData({
    ...(document.structured_data || {}),
    provider:
      document.structured_data?.provider ?? document.provider,
    client:
      document.structured_data?.client ?? document.client,
    date:
      document.structured_data?.date ?? document.invoice_date,
    invoice_number:
      document.structured_data?.invoice_number ?? document.invoice_number,
    supplier_ice:
      document.structured_data?.supplier_ice ??
      document.supplier_ice ??
      document.ice,
    client_ice:
      document.structured_data?.client_ice ?? document.client_ice,
    rc: document.structured_data?.rc ?? document.rc,
    if_number:
      document.structured_data?.if_number ?? document.if_number,
    cnss: document.structured_data?.cnss ?? document.cnss,
    tva_percentage:
      document.structured_data?.tva_percentage ?? document.tva_percentage,
    tva: document.structured_data?.tva ?? document.tva,
    total_ht:
      document.structured_data?.total_ht ?? document.total_ht,
    total_ttc:
      document.structured_data?.total_ttc ?? document.total_ttc,
    calculated_fields:
      document.structured_data?.calculated_fields ??
      document.calculated_fields ??
      [],
    calculation_details:
      document.structured_data?.calculation_details ??
      document.calculation_details ??
      [],
    warnings:
      document.structured_data?.warnings ?? document.warnings ?? [],
  });

function InvoiceField({
  label,
  value,
  field,
  canEdit,
  onChange,
  emphasis = false,
  badge = null,
}) {
  return (
    <div>
      <div className="flex items-center justify-between gap-2">
        <label className="text-xs font-semibold text-gray-400 uppercase">
          {label}
        </label>
        {badge}
      </div>

      <input
        type="text"
        readOnly={!canEdit}
        value={value ?? ''}
        onChange={(event) => onChange(field, event.target.value)}
        className={`
          w-full mt-1 px-3 py-2 border rounded-lg font-medium
          focus:ring-2 focus:ring-blue-500/20 focus:outline-none
          ${
            canEdit
              ? emphasis
                ? 'text-green-700 bg-green-50/50 border-green-200'
                : 'text-gray-700 bg-white'
              : 'text-gray-500 bg-gray-50 cursor-not-allowed'
          }
        `}
      />
    </div>
  );
}

function Dashboard() {
  const navigate = useNavigate();
  const fileInputRef = useRef(null);

  const [selectedFiles, setSelectedFiles] = useState([]);
  const [processing, setProcessing] = useState(false);
  const [progress, setProgress] = useState({ current: 0, total: 0 });
  const [groupResults, setGroupResults] = useState([]);
  const [currentLot, setCurrentLot] = useState(null);
  const [processingError, setProcessingError] = useState('');
  const [processingMessage, setProcessingMessage] = useState('');

  const [history, setHistory] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState('created_at');
  const [sortOrder, setSortOrder] = useState('desc');
  const [userRole, setUserRole] = useState(null);

  const [currentDocId, setCurrentDocId] = useState(null);
  const [currentFilename, setCurrentFilename] = useState('');
  const [extractedText, setExtractedText] = useState('');
  const [structuredData, setStructuredData] = useState(null);
  const [iceVerification, setIceVerification] = useState({
    ...EMPTY_ICE_VERIFICATION,
  });
  const [isValidated, setIsValidated] = useState(false);
  const [activeTab, setActiveTab] = useState('structured');
  const [validating, setValidating] = useState(false);
  const [editorError, setEditorError] = useState('');
  const [editorMessage, setEditorMessage] = useState('');

  const canValidate = userRole === 'admin' || userRole === 'comptable';
  const canEditFields = canValidate;

  useEffect(() => {
    fetchHistory();
    fetchCurrentUser();
  }, []);

  const fetchCurrentUser = async () => {
    try {
      const response = await api.get('/users/me');
      setUserRole(response.data.role);
    } catch (error) {
      console.error('Erreur lors de la récupération du profil :', error);
    }
  };

  const fetchHistory = async (
    currentSortBy = sortBy,
    currentSortOrder = sortOrder,
  ) => {
    try {
      const response = await api.get('/ocr/history', {
        params: {
          sort_by: currentSortBy,
          order: currentSortOrder,
        },
      });
      setHistory(Array.isArray(response.data) ? response.data : []);
    } catch (error) {
      console.error("Erreur lors de la récupération de l'historique :", error);
    }
  };

  const handleSortChange = (field) => {
    const nextOrder =
      sortBy === field && sortOrder === 'asc' ? 'desc' : 'asc';

    setSortBy(field);
    setSortOrder(nextOrder);
    fetchHistory(field, nextOrder);
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    navigate('/login');
  };

  const addFiles = (files) => {
    const incomingFiles = Array.from(files || []);
    const supportedFiles = incomingFiles.filter(isSupportedFile);
    const rejectedCount = incomingFiles.length - supportedFiles.length;

    if (rejectedCount > 0) {
      setProcessingError(
        `${rejectedCount} fichier(s) ignoré(s). ` +
          'Seules les images et les fichiers PDF sont acceptés.',
      );
    } else {
      setProcessingError('');
    }

    if (supportedFiles.length === 0) {
      return;
    }

    setSelectedFiles((previousFiles) => {
      const uniqueFiles = [...previousFiles];

      supportedFiles.forEach((file) => {
        const alreadySelected = uniqueFiles.some(
          (existingFile) =>
            existingFile.name === file.name &&
            existingFile.size === file.size &&
            existingFile.lastModified === file.lastModified,
        );

        if (!alreadySelected) {
          uniqueFiles.push(file);
        }
      });

      return uniqueFiles;
    });

    setGroupResults([]);
    setCurrentLot(null);
    setProcessingMessage('');
  };

  const handleFilesChange = (event) => {
    addFiles(event.target.files);
    event.target.value = '';
  };

  const handleDragOver = (event) => {
    event.preventDefault();
  };

  const handleDrop = (event) => {
    event.preventDefault();
    addFiles(event.dataTransfer.files);
  };

  const removeSelectedFile = (index) => {
    setSelectedFiles((files) =>
      files.filter((_, fileIndex) => fileIndex !== index),
    );
  };

  const clearSelection = () => {
    setSelectedFiles([]);
    setProcessingError('');
  };

  const openDocument = (document = {}) => {
    setCurrentDocId(document.id ?? null);
    setCurrentFilename(document.filename || 'Facture');
    setExtractedText(document.extracted_text || '');
    setStructuredData(documentToStructuredData(document));
    setIceVerification(
      normalizeIceVerification(
        document.ice_verification || document,
      ),
    );
    setIsValidated(Boolean(document.is_validated));
    setActiveTab('structured');
    setEditorError('');
    setEditorMessage('');
  };

  const handleProcessGroup = async () => {
    if (selectedFiles.length === 0 || processing) {
      return;
    }

    setProcessing(true);
    setProcessingError('');
    setProcessingMessage('');
    setGroupResults([]);
    setCurrentLot(null);
    setProgress({ current: 0, total: selectedFiles.length });

    try {
      const lotResponse = await api.post('/lots', {});
      const lot = lotResponse.data;
      setCurrentLot(lot);

      const results = [];

      for (let index = 0; index < selectedFiles.length; index += 1) {
        const currentFile = selectedFiles[index];

        setProgress({ current: index + 1, total: selectedFiles.length });

        if (index > 0) {
          await new Promise((resolve) => setTimeout(resolve, 1200));
        }

        try {
          const formData = new FormData();
          formData.append('file', currentFile);

          const extractResponse = await api.post('/ocr/extract', formData);
          const extractionData = extractResponse.data || {};

          const extractedDocuments = Array.isArray(extractionData.documents)
            ? extractionData.documents
            : extractionData.id
              ? [extractionData]
              : [];

          console.log('Réponse OCR reçue :', extractionData);
          console.log('Factures détectées :', extractedDocuments);

          if (extractedDocuments.length === 0) {
            throw new Error("Aucune facture n'a été extraite.");
          }

          for (const extractedDocument of extractedDocuments) {
            await api.put(`/ocr/documents/${extractedDocument.id}/lot`, {
              lot_id: lot.id,
            });

            const result = {
              ...extractedDocument,
              id: extractedDocument.id,
              filename: extractedDocument.filename || currentFile.name,
              source_filename:
                extractedDocument.source_filename || currentFile.name,
              source_pages: extractedDocument.source_pages || [],
              invoice_reference:
                extractedDocument.invoice_reference ||
                extractedDocument.invoice_number ||
                extractedDocument.structured_data?.invoice_number ||
                null,
              extracted_text: extractedDocument.extracted_text || '',
              structured_data: documentToStructuredData(extractedDocument),
              ice_verification: normalizeIceVerification(
                extractedDocument.ice_verification || extractedDocument,
              ),
              is_validated: Boolean(extractedDocument.is_validated),
              lot_id: lot.id,
              status: 'done',
            };

            results.push(result);
          }

          const extractionErrors = extractionData.errors || [];

          for (const extractionError of extractionErrors) {
            results.push({
              filename:
                `${currentFile.name} - facture ` +
                `${extractionError.invoice_index}`,
              status: 'error',
              error_message:
                extractionError.message ||
                'Erreur lors du traitement de cette facture.',
            });
          }

          setGroupResults([...results]);
        } catch (error) {
          console.error(`Erreur OCR pour ${currentFile.name} :`, error);

          results.push({
            filename: currentFile.name,
            status: 'error',
            error_message: getApiErrorMessage(
              error,
              'Erreur lors du traitement OCR de ce document.',
            ),
          });

          setGroupResults([...results]);
        }
      }

      const successCount = results.filter(
        (result) => result.status === 'done',
      ).length;
      const errorCount = results.length - successCount;

      setSelectedFiles([]);
      setProcessingMessage(
        `${successCount} facture(s) enregistrée(s) dans ${lot.reference}` +
          (errorCount > 0 ? `, avec ${errorCount} échec(s).` : '.'),
      );

      await fetchHistory();

      const firstSuccessfulResult = results.find(
        (result) => result.status === 'done',
      );

      if (firstSuccessfulResult) {
        openDocument(firstSuccessfulResult);
      }
    } catch (error) {
      console.error('Erreur traitement OCR :', error);
      setProcessingError(
        getApiErrorMessage(error, 'Impossible de traiter les factures.'),
      );
    } finally {
      setProcessing(false);
    }
  };

  const handleSelectHistory = (doc) => {
    openDocument({
      ...doc,
      structured_data: documentToStructuredData(doc),
      ice_verification: normalizeIceVerification(doc),
    });
  };

  const handleValidate = async () => {
    if (!currentDocId || !structuredData) {
      setEditorError('Aucun document sélectionné.');
      return;
    }

    setValidating(true);
    setEditorError('');
    setEditorMessage('');

    try {
      const payload = {
        provider: structuredData.provider || MISSING,
        client: structuredData.client || MISSING,
        date: structuredData.date || MISSING_DATE,
        invoice_number: structuredData.invoice_number || MISSING,
        ice: structuredData.ice || MISSING,
        client_ice: structuredData.client_ice || MISSING,
        rc: structuredData.rc || MISSING,
        if_number: structuredData.if_number || MISSING,
        cnss: structuredData.cnss || MISSING,
        tva_percentage: structuredData.tva_percentage || MISSING,
        tva: structuredData.tva || MISSING,
        total_ht: structuredData.total_ht || MISSING,
        total_ttc: structuredData.total_ttc || MISSING,
      };

      const response = await api.put(
        `/ocr/documents/${currentDocId}/validate`,
        payload,
      );

      const updatedDocument = response.data || {};
      const updatedStructured = documentToStructuredData({
        ...updatedDocument,
        structured_data: {
          ...structuredData,
          ...updatedDocument,
          date: updatedDocument.invoice_date || structuredData.date,
          supplier_ice: updatedDocument.ice || structuredData.ice,
        },
      });

      setStructuredData(updatedStructured);
      setIceVerification(normalizeIceVerification(updatedDocument));
      setIsValidated(true);
      setEditorMessage('Document validé avec succès.');

      await fetchHistory();
    } catch (error) {
      console.error('Erreur validation :', error);
      setEditorError(
        getApiErrorMessage(
          error,
          'Erreur lors de la validation du document.',
        ),
      );
    } finally {
      setValidating(false);
    }
  };

  const handleExportJSON = () => {
    if (!structuredData) {
      return;
    }

    const data = {
      filename: currentFilename,
      ...structuredData,
      ice_verification: iceVerification,
      is_validated: isValidated,
    };

    const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: 'application/json;charset=utf-8',
    });

    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${currentFilename || 'facture'}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleExportExcel = () => {
    if (!structuredData) {
      return;
    }

    const wsData = [
      [
        'Fournisseur',
        'Client',
        'Date facture',
        'Numéro facture',
        'ICE fournisseur',
        'ICE client',
        'RC',
        'IF',
        'CNSS',
        'TVA %',
        'Montant TVA',
        'Total HT',
        'Total TTC',
      ],
      [
        structuredData.provider || '',
        structuredData.client || '',
        structuredData.date || '',
        structuredData.invoice_number || '',
        structuredData.ice || '',
        structuredData.client_ice || '',
        structuredData.rc || '',
        structuredData.if_number || '',
        structuredData.cnss || '',
        structuredData.tva_percentage || '',
        structuredData.tva || '',
        structuredData.total_ht || '',
        structuredData.total_ttc || '',
      ],
    ];

    const worksheet = XLSX.utils.aoa_to_sheet(wsData);
    worksheet['!cols'] = [
      { wch: 30 },
      { wch: 30 },
      { wch: 16 },
      { wch: 22 },
      { wch: 22 },
      { wch: 22 },
      { wch: 15 },
      { wch: 15 },
      { wch: 15 },
      { wch: 12 },
      { wch: 16 },
      { wch: 16 },
      { wch: 16 },
    ];

    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, 'Facture');

    const providerName = (structuredData.provider || 'facture').replace(
      /[^a-zA-Z0-9_-]/g,
      '_',
    );

    XLSX.writeFile(workbook, `facture_${providerName}.xlsx`);
  };

  const handleExportGroupExcel = () => {
    const successfulResults = groupResults.filter(
      (result) => result.status === 'done',
    );

    if (successfulResults.length === 0) {
      return;
    }

    const rows = successfulResults.map((result) => {
      const data = documentToStructuredData(result);

      return {
        Fichier: result.filename || '',
        Fournisseur: data.provider,
        Client: data.client,
        'Date facture': data.date,
        'Numéro facture': data.invoice_number,
        'ICE fournisseur': data.ice,
        'ICE client': data.client_ice,
        RC: data.rc,
        IF: data.if_number,
        CNSS: data.cnss,
        'TVA %': data.tva_percentage,
        'Montant TVA': data.tva,
        'Total HT': data.total_ht,
        'Total TTC': data.total_ttc,
      };
    });

    const worksheet = XLSX.utils.json_to_sheet(rows);
    worksheet['!cols'] = [
      { wch: 30 },
      { wch: 30 },
      { wch: 30 },
      { wch: 16 },
      { wch: 22 },
      { wch: 22 },
      { wch: 22 },
      { wch: 15 },
      { wch: 15 },
      { wch: 15 },
      { wch: 12 },
      { wch: 16 },
      { wch: 16 },
      { wch: 16 },
    ];

    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, 'Lot');
    XLSX.writeFile(
      workbook,
      `${currentLot?.reference || 'lot_factures'}.xlsx`,
    );
  };

  const updateStructuredField = (field, value) => {
    if (!canEditFields) {
      return;
    }

    setStructuredData((data) => ({
      ...(data || EMPTY_STRUCTURED_DATA),
      [field]: value,
    }));

    if (field === 'ice') {
      setIceVerification({
        status: 'non_verifie',
        company_name: null,
        message:
          "L'ICE a été modifié. Enregistrez les modifications " +
          'pour lancer une nouvelle vérification.',
        verification_url: null,
      });
    }

    setEditorError('');
    setEditorMessage('');
  };

  const filteredHistory = history.filter((document) =>
    String(document.filename || '')
      .toLowerCase()
      .includes(searchQuery.toLowerCase()),
  );

  const icePresentation = getIceVerificationPresentation(
    iceVerification?.status,
  );

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col font-sans">
      <nav className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16 items-center">
            <h1 className="text-xl font-bold text-blue-600">
              OCR Accounting Platform 🚀
            </h1>

            <div className="flex items-center gap-3">
              <NotificationBell />

              {canValidate && (
                <button
                  onClick={() => navigate('/lots')}
                  className="px-4 py-2 text-sm font-medium text-purple-600 bg-purple-50 hover:bg-purple-100 rounded-md transition-colors"
                >
                  📦 Gestion des lots
                </button>
              )}

              {userRole === 'admin' && (
                <button
                  onClick={() => navigate('/admin/users')}
                  className="px-4 py-2 text-sm font-medium text-blue-600 bg-blue-50 hover:bg-blue-100 rounded-md transition-colors"
                >
                  👥 Gestion utilisateurs
                </button>
              )}

              <button
                onClick={handleLogout}
                className="px-4 py-2 text-sm font-medium text-white bg-red-500 hover:bg-red-600 rounded-md transition-colors"
              >
                Déconnexion
              </button>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl w-full mx-auto py-10 px-4 sm:px-6 lg:px-8 grid grid-cols-1 md:grid-cols-3 gap-8 flex-1">
        <div className="md:col-span-2 space-y-6">
          <section className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
            <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 mb-6">
              <div>
                <h2 className="text-2xl font-semibold text-gray-800 mb-2">
                  📚 Traitement de plusieurs factures
                </h2>
                <p className="text-gray-600">
                  Sélectionnez une ou plusieurs factures. Chaque sélection
                  traitée crée automatiquement un nouveau lot.
                </p>
              </div>

              <span className="shrink-0 px-3 py-1.5 rounded-full bg-purple-50 text-purple-700 border border-purple-100 text-xs font-semibold">
                Lot automatique
              </span>
            </div>

            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFilesChange}
              accept="image/*,application/pdf"
              multiple
              className="hidden"
            />

            <div
              onClick={() => fileInputRef.current?.click()}
              onDragOver={handleDragOver}
              onDrop={handleDrop}
              className={`
                border-2 border-dashed rounded-xl p-9 text-center cursor-pointer
                transition-all
                ${
                  selectedFiles.length > 0
                    ? 'border-purple-400 bg-purple-50/20'
                    : 'border-gray-300 hover:border-purple-500 hover:bg-purple-50/10'
                }
              `}
            >
              <div className="text-4xl mb-2">📥</div>
              <p className="text-gray-600 font-medium">
                Cliquez ou glissez-déposez plusieurs factures
              </p>
              <p className="text-xs text-gray-400 mt-1">
                Images ou PDF — sélection multiple disponible
              </p>
            </div>

            {selectedFiles.length > 0 && (
              <div className="mt-5">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-sm font-semibold text-gray-700">
                    {selectedFiles.length} fichier(s) sélectionné(s)
                  </p>
                  <button
                    type="button"
                    onClick={clearSelection}
                    disabled={processing}
                    className="text-xs text-red-500 hover:text-red-700 disabled:opacity-40"
                  >
                    Tout retirer
                  </button>
                </div>

                <div className="space-y-2 max-h-52 overflow-y-auto pr-1">
                  {selectedFiles.map((selectedFile, index) => (
                    <div
                      key={`${selectedFile.name}-${selectedFile.size}-${selectedFile.lastModified}`}
                      className="flex justify-between items-center p-3 bg-gray-50 rounded-lg border border-gray-100"
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-gray-700 truncate">
                          {selectedFile.name}
                        </p>
                        <p className="text-xs text-gray-400">
                          {(selectedFile.size / 1024 / 1024).toFixed(2)} Mo
                        </p>
                      </div>

                      <button
                        type="button"
                        onClick={() => removeSelectedFile(index)}
                        disabled={processing}
                        className="text-xs text-red-500 hover:text-red-700 ml-3 disabled:opacity-40"
                      >
                        Retirer
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {processingError && (
              <div className="mt-4 p-3 bg-red-50 text-red-600 border border-red-200 rounded-md text-sm">
                {processingError}
              </div>
            )}

            {processingMessage && (
              <div className="mt-4 p-3 bg-green-50 text-green-700 border border-green-200 rounded-md text-sm">
                {processingMessage}
              </div>
            )}

            {selectedFiles.length > 0 && (
              <div className="mt-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <p className="text-xs text-gray-400">
                  Un lot sera créé pour ce groupe, même lorsqu'il contient un
                  seul fichier.
                </p>

                <button
                  onClick={handleProcessGroup}
                  disabled={processing}
                  className={`
                    px-6 py-2.5 rounded-lg font-medium text-white transition-colors
                    ${
                      processing
                        ? 'bg-purple-400 cursor-not-allowed'
                        : 'bg-purple-600 hover:bg-purple-700 shadow-sm'
                    }
                  `}
                >
                  {processing
                    ? `Traitement ${progress.current}/${progress.total}...`
                    : `Lancer l'OCR (${selectedFiles.length} fichier(s)) 🚀`}
                </button>
              </div>
            )}

            {processing && progress.total > 0 && (
              <div className="mt-4 h-2 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-purple-500 transition-all duration-300"
                  style={{
                    width: `${(progress.current / progress.total) * 100}%`,
                  }}
                />
              </div>
            )}

            {groupResults.length > 0 && (
              <div className="mt-7 border-t pt-6">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
                  <h3 className="text-lg font-semibold text-gray-800">
                    Résultat
                    {currentLot && (
                      <span className="text-purple-600">
                        {' '}— {currentLot.reference}
                      </span>
                    )}
                  </h3>

                  <button
                    onClick={handleExportGroupExcel}
                    disabled={
                      !groupResults.some((result) => result.status === 'done')
                    }
                    className="bg-emerald-700 hover:bg-emerald-800 text-white px-4 py-2 rounded-lg text-sm font-medium shadow-sm transition-colors disabled:opacity-40"
                  >
                    📊 Exporter le lot en Excel
                  </button>
                </div>

                <div className="space-y-2">
                  {groupResults.map((result, index) => (
                    <div
                      key={result.id || `${result.filename}-${index}`}
                      className={`
                        flex flex-col sm:flex-row sm:items-center sm:justify-between
                        gap-3 p-3 rounded-lg border
                        ${
                          result.status === 'done'
                            ? 'border-green-100 bg-green-50/30'
                            : 'border-red-100 bg-red-50/30'
                        }
                      `}
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-gray-700 truncate">
                          {result.filename}
                        </p>

                        {result.status === 'done' ? (
                          <p className="text-xs text-gray-400">
                            {result.structured_data?.provider} —{' '}
                            {result.structured_data?.invoice_number} —{' '}
                            {result.structured_data?.total_ttc}
                          </p>
                        ) : (
                          <p className="text-xs text-red-500">
                            {result.error_message}
                          </p>
                        )}
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        {result.status === 'done' && (
                          <button
                            type="button"
                            onClick={() => openDocument(result)}
                            className="px-3 py-1.5 rounded-md text-xs font-semibold bg-blue-50 text-blue-700 hover:bg-blue-100 border border-blue-100"
                          >
                            {canEditFields ? '✏️ Modifier' : '👁️ Consulter'}
                          </button>
                        )}

                        <span
                          className={`
                            text-xs font-medium px-2 py-1 rounded-full
                            ${
                              result.status === 'done'
                                ? 'bg-green-100 text-green-700'
                                : 'bg-red-100 text-red-700'
                            }
                          `}
                        >
                          {result.status === 'done' ? '✓ Traité' : '✗ Échec'}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>

          {structuredData && currentDocId && (
            <section className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
              <div className="border-b bg-gray-50 px-6 py-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <div>
                  <p className="text-xs text-gray-400 uppercase font-semibold">
                    Facture sélectionnée
                  </p>
                  <h3 className="font-semibold text-gray-800 truncate">
                    {currentFilename}
                  </h3>
                </div>

                <span
                  className={`
                    px-3 py-1 rounded-full text-xs font-medium border
                    self-start sm:self-auto
                    ${
                      isValidated
                        ? 'bg-green-100 text-green-700 border-green-200'
                        : 'bg-amber-100 text-amber-700 border-amber-200'
                    }
                  `}
                >
                  {isValidated ? '✓ Validée' : '⏳ En attente de validation'}
                </span>
              </div>

              <div className="px-6 pt-4 border-b flex gap-4">
                <button
                  onClick={() => setActiveTab('structured')}
                  className={`
                    pb-3 text-sm font-medium border-b-2 transition-colors
                    ${
                      activeTab === 'structured'
                        ? 'border-blue-600 text-blue-600'
                        : 'border-transparent text-gray-500 hover:text-gray-700'
                    }
                  `}
                >
                  📈 Données extraites
                </button>

                <button
                  onClick={() => setActiveTab('raw')}
                  className={`
                    pb-3 text-sm font-medium border-b-2 transition-colors
                    ${
                      activeTab === 'raw'
                        ? 'border-blue-600 text-blue-600'
                        : 'border-transparent text-gray-500 hover:text-gray-700'
                    }
                  `}
                >
                  📝 Texte brut OCR
                </button>
              </div>

              <div className="p-6">
                {editorError && (
                  <div className="mb-4 p-3 bg-red-50 text-red-600 border border-red-200 rounded-md text-sm">
                    {editorError}
                  </div>
                )}

                {editorMessage && (
                  <div className="mb-4 p-3 bg-green-50 text-green-700 border border-green-200 rounded-md text-sm">
                    {editorMessage}
                  </div>
                )}

                {activeTab === 'structured' && (
                  <div className="space-y-5">
                    {!canEditFields && (
                      <p className="text-xs text-gray-400 italic">
                        Les données sont en lecture seule. Seul un comptable ou
                        un administrateur peut les modifier et les valider.
                      </p>
                    )}

                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                      <InvoiceField
                        label="Fournisseur"
                        field="provider"
                        value={structuredData.provider}
                        canEdit={canEditFields}
                        onChange={updateStructuredField}
                      />

                      <InvoiceField
                        label="Client"
                        field="client"
                        value={structuredData.client}
                        canEdit={canEditFields}
                        onChange={updateStructuredField}
                      />

                      <InvoiceField
                        label="Date facture"
                        field="date"
                        value={structuredData.date}
                        canEdit={canEditFields}
                        onChange={updateStructuredField}
                      />

                      <InvoiceField
                        label="Numéro facture"
                        field="invoice_number"
                        value={structuredData.invoice_number}
                        canEdit={canEditFields}
                        onChange={updateStructuredField}
                      />

                      <InvoiceField
                        label="ICE fournisseur"
                        field="ice"
                        value={structuredData.ice}
                        canEdit={canEditFields}
                        onChange={updateStructuredField}
                        badge={
                          <span
                            className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border ${icePresentation.badgeClass}`}
                          >
                            {icePresentation.icon} {icePresentation.label}
                          </span>
                        }
                      />

                      <InvoiceField
                        label="ICE client"
                        field="client_ice"
                        value={structuredData.client_ice}
                        canEdit={canEditFields}
                        onChange={updateStructuredField}
                      />

                      <InvoiceField
                        label="RC"
                        field="rc"
                        value={structuredData.rc}
                        canEdit={canEditFields}
                        onChange={updateStructuredField}
                      />

                      <InvoiceField
                        label="IF"
                        field="if_number"
                        value={structuredData.if_number}
                        canEdit={canEditFields}
                        onChange={updateStructuredField}
                      />

                      <InvoiceField
                        label="CNSS"
                        field="cnss"
                        value={structuredData.cnss}
                        canEdit={canEditFields}
                        onChange={updateStructuredField}
                      />

                      <InvoiceField
                        label="TVA %"
                        field="tva_percentage"
                        value={structuredData.tva_percentage}
                        canEdit={canEditFields}
                        onChange={updateStructuredField}
                      />

                      <InvoiceField
                        label="Montant TVA"
                        field="tva"
                        value={structuredData.tva}
                        canEdit={canEditFields}
                        onChange={updateStructuredField}
                      />

                      <InvoiceField
                        label="Total HT"
                        field="total_ht"
                        value={structuredData.total_ht}
                        canEdit={canEditFields}
                        onChange={updateStructuredField}
                      />

                      <InvoiceField
                        label="Total TTC"
                        field="total_ttc"
                        value={structuredData.total_ttc}
                        canEdit={canEditFields}
                        onChange={updateStructuredField}
                        emphasis
                      />
                    </div>

                    <div
                      className={`p-4 rounded-xl border ${icePresentation.containerClass}`}
                    >
                      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                        <div className="flex gap-3">
                          <span className="text-2xl">{icePresentation.icon}</span>
                          <div>
                            <p className="text-sm font-semibold">
                              Vérification de l’ICE fournisseur
                            </p>
                            <p className="text-sm mt-1">
                              {iceVerification?.message ||
                                'Aucun résultat de vérification.'}
                            </p>

                            {iceVerification?.company_name && (
                              <div className="mt-3 px-3 py-2 bg-white/70 rounded-lg border border-current/10">
                                <p className="text-[11px] font-semibold uppercase opacity-60">
                                  Société trouvée
                                </p>
                                <p className="text-sm font-bold mt-1">
                                  🏢 {iceVerification.company_name}
                                </p>
                              </div>
                            )}
                          </div>
                        </div>

                        {iceVerification?.verification_url && (
                          <a
                            href={iceVerification.verification_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="shrink-0 px-3 py-2 bg-white rounded-lg border border-current/20 text-xs font-semibold hover:shadow-sm transition-shadow"
                          >
                            Vérifier sur ICE Maroc ↗
                          </a>
                        )}
                      </div>

                      {iceVerification?.status ===
                        'valide_mathematiquement' && (
                        <p className="mt-3 text-xs opacity-70 border-t border-current/10 pt-3">
                          Cette validation confirme le format et la clé de
                          contrôle de l’ICE. Elle ne confirme pas
                          automatiquement l’identité officielle de la société.
                        </p>
                      )}
                    </div>

                    {structuredData.calculated_fields?.length > 0 && (
                      <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                        <p className="text-sm font-semibold text-blue-700 mb-2">
                          🧮 Valeurs calculées automatiquement
                        </p>
                        {structuredData.calculation_details?.length > 0 ? (
                          structuredData.calculation_details.map(
                            (detail, index) => (
                              <p
                                key={`${detail}-${index}`}
                                className="text-sm text-blue-600"
                              >
                                • {detail}
                              </p>
                            ),
                          )
                        ) : (
                          <p className="text-sm text-blue-600">
                            Certains champs ont été calculés automatiquement.
                          </p>
                        )}
                      </div>
                    )}

                    {structuredData.warnings?.length > 0 && (
                      <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg">
                        <p className="text-sm font-semibold text-amber-700 mb-2">
                          ⚠️ Avertissements
                        </p>
                        {structuredData.warnings.map((warning, index) => (
                          <p
                            key={`${warning}-${index}`}
                            className="text-sm text-amber-700"
                          >
                            • {warning}
                          </p>
                        ))}
                      </div>
                    )}

                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pt-4 border-t mt-4">
                      <div className="flex gap-2">
                        <button
                          onClick={handleExportJSON}
                          className="bg-gray-800 hover:bg-gray-900 text-white px-4 py-2 rounded-lg text-sm font-medium shadow-sm transition-colors"
                        >
                          📥 JSON
                        </button>

                        <button
                          onClick={handleExportExcel}
                          className="bg-emerald-700 hover:bg-emerald-800 text-white px-4 py-2 rounded-lg text-sm font-medium shadow-sm transition-colors"
                        >
                          📊 Excel
                        </button>
                      </div>

                      {canValidate && currentDocId && (
                        <button
                          onClick={handleValidate}
                          disabled={validating}
                          className={`
                            px-5 py-2 rounded-lg font-medium shadow-sm
                            transition-colors text-white
                            ${
                              validating
                                ? 'bg-green-400 cursor-not-allowed'
                                : isValidated
                                  ? 'bg-emerald-700 hover:bg-emerald-800'
                                  : 'bg-green-600 hover:bg-green-700'
                            }
                          `}
                        >
                          {validating
                            ? 'Enregistrement...'
                            : isValidated
                              ? '🔄 Enregistrer les modifications'
                              : '✓ Valider les données'}
                        </button>
                      )}
                    </div>
                  </div>
                )}

                {activeTab === 'raw' && (
                  <textarea
                    value={extractedText}
                    readOnly
                    rows={16}
                    className="w-full p-4 border border-gray-300 rounded-lg bg-gray-50 text-gray-700 font-mono text-sm focus:outline-none"
                  />
                )}
              </div>
            </section>
          )}
        </div>

        <aside className="bg-white p-6 rounded-xl shadow-sm border border-gray-200 h-[680px] flex flex-col">
          <h3 className="text-lg font-semibold text-gray-800 mb-2 flex items-center gap-2">
            <span>📂</span>
            Historique des analyses
          </h3>

          <div className="mb-4">
            <input
              type="text"
              placeholder="🔍 Rechercher une facture..."
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            />

            <div className="flex gap-2 mt-2">
              {[
                { field: 'created_at', label: 'Date' },
                { field: 'provider', label: 'Fournisseur' },
                { field: 'client', label: 'Client' },
              ].map(({ field, label }) => (
                <button
                  key={field}
                  type="button"
                  onClick={() => handleSortChange(field)}
                  className={`
                    px-2.5 py-1 rounded-md text-xs font-medium border transition-colors
                    ${
                      sortBy === field
                        ? 'bg-blue-50 text-blue-700 border-blue-200'
                        : 'bg-gray-50 text-gray-500 border-gray-200 hover:bg-gray-100'
                    }
                  `}
                >
                  {label}
                  {sortBy === field && (sortOrder === 'asc' ? ' ↑' : ' ↓')}
                </button>
              ))}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto space-y-3 pr-1">
            {filteredHistory.length === 0 ? (
              <p className="text-sm text-gray-400 italic text-center mt-10">
                Aucun document trouvé.
              </p>
            ) : (
              filteredHistory.map((document) => (
                <button
                  type="button"
                  key={document.id}
                  onClick={() => handleSelectHistory(document)}
                  className={`
                    w-full text-left p-3 border rounded-xl hover:bg-blue-50/40
                    hover:border-blue-200 cursor-pointer transition-all shadow-sm
                    ${
                      currentDocId === document.id
                        ? 'border-blue-300 bg-blue-50/40'
                        : 'border-gray-100'
                    }
                  `}
                >
                  <div className="flex justify-between items-start gap-2">
                    <p className="text-sm font-semibold text-gray-700 truncate">
                      {document.filename}
                    </p>

                    <span
                      className={`
                        shrink-0 px-2 py-0.5 rounded-full text-[10px]
                        font-medium border
                        ${
                          document.is_validated
                            ? 'bg-green-100 text-green-700 border-green-200'
                            : 'bg-amber-100 text-amber-700 border-amber-200'
                        }
                      `}
                    >
                      {document.is_validated ? 'Validée' : 'En attente'}
                    </span>
                  </div>

                  <div className="mt-1 text-xs text-gray-500 truncate">
                    {document.provider || MISSING}
                    {document.invoice_number
                      ? ` — ${document.invoice_number}`
                      : ''}
                  </div>

                  <div className="flex items-center justify-between mt-1 gap-2">
                    <span className="text-xs text-gray-400">
                      {document.created_at
                        ? new Date(document.created_at).toLocaleDateString(
                            'fr-FR',
                          )
                        : ''}
                    </span>

                    {document.lot_id && (
                      <span className="text-[10px] text-purple-600 bg-purple-50 px-2 py-0.5 rounded-full">
                        Lot #{document.lot_id}
                      </span>
                    )}
                  </div>
                </button>
              ))
            )}
          </div>
        </aside>
      </main>
    </div>
  );
}

export default Dashboard;