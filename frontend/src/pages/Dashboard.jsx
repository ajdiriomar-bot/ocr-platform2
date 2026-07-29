import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import * as XLSX from 'xlsx';
import api from '../api';

const EMPTY_STRUCTURED_DATA = {
  provider: 'Non détecté',
  client: 'Non détecté',
  date: 'Non détectée',
  ice: 'Non détecté',
  if_number: 'Non détecté',
  rc: 'Non détecté',
  total_ht: '0.00',
  tva: '0.00',
  total_ttc: '0.00',
};

const isSupportedFile = (file) =>
  file?.type?.startsWith('image/') ||
  file?.type === 'application/pdf';

const normalizeStructuredData = (data = {}) => ({
  ...EMPTY_STRUCTURED_DATA,
  ...data,
  date:
    data.date ??
    data.invoice_date ??
    EMPTY_STRUCTURED_DATA.date,
});

const documentToStructuredData = (document) =>
  normalizeStructuredData({
    provider: document.provider,
    client: document.client,
    date: document.invoice_date,
    ice: document.ice,
    if_number: document.if_number,
    rc: document.rc,
    total_ht: document.total_ht,
    tva: document.tva,
    total_ttc: document.total_ttc,
  });

function Dashboard() {
  const navigate = useNavigate();
  const fileInputRef = useRef(null);

  const [selectedFiles, setSelectedFiles] = useState([]);
  const [processing, setProcessing] = useState(false);

  const [progress, setProgress] = useState({
    current: 0,
    total: 0,
  });

  const [groupResults, setGroupResults] = useState([]);
  const [currentLot, setCurrentLot] = useState(null);
  const [processingError, setProcessingError] = useState('');
  const [processingMessage, setProcessingMessage] = useState('');

  const [history, setHistory] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [userRole, setUserRole] = useState(null);

  const [currentDocId, setCurrentDocId] = useState(null);
  const [currentFilename, setCurrentFilename] = useState('');
  const [extractedText, setExtractedText] = useState('');
  const [structuredData, setStructuredData] = useState(null);
  const [isValidated, setIsValidated] = useState(false);
  const [activeTab, setActiveTab] = useState('structured');
  const [validating, setValidating] = useState(false);
  const [editorError, setEditorError] = useState('');
  const [editorMessage, setEditorMessage] = useState('');

  const canValidate =
    userRole === 'admin' ||
    userRole === 'comptable';

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
      console.error(
        'Erreur lors de la récupération du profil :',
        error,
      );
    }
  };

  const fetchHistory = async () => {
    try {
      const response = await api.get('/ocr/history');
      setHistory(response.data);
    } catch (error) {
      console.error(
        "Erreur lors de la récupération de l'historique :",
        error,
      );
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    navigate('/login');
  };

  const addFiles = (files) => {
    const incomingFiles = Array.from(files || []);

    const supportedFiles = incomingFiles.filter(
      isSupportedFile,
    );

    const rejectedCount =
      incomingFiles.length - supportedFiles.length;

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

    // Permet de sélectionner à nouveau le même fichier.
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
      files.filter(
        (_, fileIndex) => fileIndex !== index,
      ),
    );
  };

  const clearSelection = () => {
    setSelectedFiles([]);
    setProcessingError('');
  };

  const openDocument = ({
    id,
    filename,
    extracted_text,
    structured_data,
    is_validated,
  }) => {
    setCurrentDocId(id);
    setCurrentFilename(filename || 'Facture');
    setExtractedText(extracted_text || '');

    setStructuredData(
      normalizeStructuredData(structured_data),
    );

    setIsValidated(Boolean(is_validated));
    setActiveTab('structured');
    setEditorError('');
    setEditorMessage('');
  };

  const handleProcessGroup = async () => {
    if (
      selectedFiles.length === 0 ||
      processing
    ) {
      return;
    }

    setProcessing(true);
    setProcessingError('');
    setProcessingMessage('');
    setGroupResults([]);
    setCurrentLot(null);

    setProgress({
      current: 0,
      total: selectedFiles.length,
    });

    try {
      /*
       * Un nouveau lot est automatiquement créé
       * pour chaque groupe de fichiers sélectionné.
       */
      const lotResponse = await api.post('/lots', {});

      const lot = lotResponse.data;

      setCurrentLot(lot);

      const results = [];

      /*
       * Les factures sont traitées une par une
       * pour éviter de surcharger le service OCR.
       */
      for (
        let index = 0;
        index < selectedFiles.length;
        index += 1
      ) {
        const currentFile = selectedFiles[index];

        setProgress({
          current: index + 1,
          total: selectedFiles.length,
        });

        if (index > 0) {
          await new Promise((resolve) =>
            setTimeout(resolve, 1200),
          );
        }

        try {
          const formData = new FormData();
          formData.append('file', currentFile);

          const extractResponse = await api.post(
            '/ocr/extract',
            formData,
          );

          const extractedDocument =
            extractResponse.data;

          /*
           * La facture extraite est immédiatement
           * rattachée au lot créé précédemment.
           */
          await api.put(
            `/ocr/documents/${extractedDocument.id}/lot`,
            {
              lot_id: lot.id,
            },
          );

          const result = {
            id: extractedDocument.id,
            filename: currentFile.name,
            extracted_text:
              extractedDocument.extracted_text,
            structured_data:
              normalizeStructuredData(
                extractedDocument.structured_data,
              ),
            is_validated: Boolean(
              extractedDocument.is_validated,
            ),
            lot_id: lot.id,
            status: 'done',
          };

          results.push(result);
          setGroupResults([...results]);
        } catch (error) {
          results.push({
            filename: currentFile.name,
            status: 'error',
            error_message:
              error.response?.data?.detail ||
              (
                'Erreur lors du traitement OCR ' +
                'de cette facture.'
              ),
          });

          setGroupResults([...results]);
        }
      }

      const successCount = results.filter(
        (result) => result.status === 'done',
      ).length;

      const errorCount =
        results.length - successCount;

      setSelectedFiles([]);

      setProcessingMessage(
        `${successCount} facture(s) enregistrée(s) ` +
          `dans ${lot.reference}` +
          (
            errorCount > 0
              ? `, avec ${errorCount} échec(s).`
              : '.'
          ),
      );

      await fetchHistory();

      const firstSuccessfulResult = results.find(
        (result) => result.status === 'done',
      );

      if (firstSuccessfulResult) {
        openDocument(firstSuccessfulResult);
      }
    } catch (error) {
      setProcessingError(
        error.response?.data?.detail ||
          (
            'Impossible de créer le lot pour ' +
            'ce groupe de factures.'
          ),
      );
    } finally {
      setProcessing(false);
    }
  };

  const handleSelectHistory = (document) => {
    openDocument({
      id: document.id,
      filename: document.filename,
      extracted_text: document.extracted_text,
      structured_data:
        documentToStructuredData(document),
      is_validated: document.is_validated,
    });
  };

  const handleValidate = async () => {
    if (!currentDocId || !structuredData) {
      return;
    }

    setValidating(true);
    setEditorError('');
    setEditorMessage('');

    try {
      await api.put(
        `/ocr/documents/${currentDocId}/validate`,
        structuredData,
      );

      setIsValidated(true);

      setEditorMessage(
        (
          'Les données de la facture ont été ' +
          'enregistrées avec succès.'
        ),
      );

      setGroupResults((results) =>
        results.map((result) =>
          result.id === currentDocId
            ? {
                ...result,
                structured_data: {
                  ...structuredData,
                },
                is_validated: true,
              }
            : result,
        ),
      );

      await fetchHistory();
    } catch (error) {
      setEditorError(
        error.response?.data?.detail ||
          (
            'Erreur lors de la modification ' +
            'de la facture.'
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

    const dataUrl =
      'data:text/json;charset=utf-8,' +
      encodeURIComponent(
        JSON.stringify(
          structuredData,
          null,
          2,
        ),
      );

    const downloadAnchor =
      document.createElement('a');

    const provider =
      structuredData.provider || 'facture';

    downloadAnchor.setAttribute(
      'href',
      dataUrl,
    );

    downloadAnchor.setAttribute(
      'download',
      (
        `facture_${provider.replace(/\s+/g, '_')}` +
        '.json'
      ),
    );

    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  const handleExportExcel = () => {
    if (!structuredData) {
      return;
    }

    const worksheet = XLSX.utils.aoa_to_sheet([
      [
        'Fournisseur',
        'Client',
        'ICE',
        'IF',
        'RC',
        'Date Facture',
        'Total HT',
        'TVA',
        'Total TTC',
      ],
      [
        structuredData.provider,
        structuredData.client,
        structuredData.ice,
        structuredData.if_number,
        structuredData.rc,
        structuredData.date,
        structuredData.total_ht,
        structuredData.tva,
        structuredData.total_ttc,
      ],
    ]);

    worksheet['!cols'] = [
      { wch: 25 },
      { wch: 25 },
      { wch: 15 },
      { wch: 12 },
      { wch: 12 },
      { wch: 15 },
      { wch: 15 },
      { wch: 10 },
      { wch: 15 },
    ];

    const workbook =
      XLSX.utils.book_new();

    XLSX.utils.book_append_sheet(
      workbook,
      worksheet,
      'Facture',
    );

    const provider =
      structuredData.provider || 'facture';

    XLSX.writeFile(
      workbook,
      (
        `facture_${provider.replace(/\s+/g, '_')}` +
        '.xlsx'
      ),
    );
  };

  const handleExportGroupExcel = () => {
    const successfulResults =
      groupResults.filter(
        (result) =>
          result.status === 'done' &&
          result.structured_data,
      );

    if (successfulResults.length === 0) {
      return;
    }

    const rows = [
      [
        'Fichier',
        'Fournisseur',
        'Client',
        'ICE',
        'IF',
        'RC',
        'Date Facture',
        'Total HT',
        'TVA',
        'Total TTC',
      ],
    ];

    successfulResults.forEach((result) => {
      const data = result.structured_data;

      rows.push([
        result.filename,
        data.provider,
        data.client,
        data.ice,
        data.if_number,
        data.rc,
        data.date,
        data.total_ht,
        data.tva,
        data.total_ttc,
      ]);
    });

    const worksheet =
      XLSX.utils.aoa_to_sheet(rows);

    worksheet['!cols'] = [
      { wch: 28 },
      { wch: 25 },
      { wch: 25 },
      { wch: 16 },
      { wch: 14 },
      { wch: 14 },
      { wch: 16 },
      { wch: 15 },
      { wch: 12 },
      { wch: 15 },
    ];

    const workbook =
      XLSX.utils.book_new();

    XLSX.utils.book_append_sheet(
      workbook,
      worksheet,
      'Lot de factures',
    );

    XLSX.writeFile(
      workbook,
      `${currentLot?.reference || 'lot_factures'}.xlsx`,
    );
  };

  const updateStructuredField = (
    field,
    value,
  ) => {
    if (!canEditFields) {
      return;
    }

    setStructuredData((data) => ({
      ...data,
      [field]: value,
    }));

    setEditorMessage('');
  };

  const filteredHistory = history.filter(
    (document) =>
      document.filename
        .toLowerCase()
        .includes(searchQuery.toLowerCase()),
  );

  const inputClassName = `
    w-full mt-1 px-3 py-2 border rounded-lg
    font-medium focus:ring-2 focus:ring-blue-500/20
    ${
      canEditFields
        ? 'text-gray-700 bg-white'
        : (
            'text-gray-500 bg-gray-50 ' +
            'cursor-not-allowed'
          )
    }
  `;

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col font-sans">
      <nav className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16 items-center">
            <h1 className="text-xl font-bold text-blue-600">
              OCR Accounting Platform 🚀
            </h1>

            <div className="flex items-center gap-3">
              {canValidate && (
                <button
                  onClick={() => navigate('/lots')}
                  className="
                    px-4 py-2 text-sm font-medium
                    text-purple-600 bg-purple-50
                    hover:bg-purple-100 rounded-md
                    transition-colors
                  "
                >
                  📦 Gestion des lots
                </button>
              )}

              {userRole === 'admin' && (
                <button
                  onClick={() =>
                    navigate('/admin/users')
                  }
                  className="
                    px-4 py-2 text-sm font-medium
                    text-blue-600 bg-blue-50
                    hover:bg-blue-100 rounded-md
                    transition-colors
                  "
                >
                  👥 Gestion utilisateurs
                </button>
              )}

              <button
                onClick={handleLogout}
                className="
                  px-4 py-2 text-sm font-medium
                  text-white bg-red-500
                  hover:bg-red-600 rounded-md
                  transition-colors
                "
              >
                Déconnexion
              </button>
            </div>
          </div>
        </div>
      </nav>

      <main
        className="
          max-w-7xl w-full mx-auto py-10
          px-4 sm:px-6 lg:px-8
          grid grid-cols-1 md:grid-cols-3
          gap-8 flex-1
        "
      >
        <div className="md:col-span-2 space-y-6">
          <section
            className="
              bg-white p-6 rounded-xl shadow-sm
              border border-gray-200
            "
          >
            <div
              className="
                flex flex-col sm:flex-row
                sm:items-start sm:justify-between
                gap-4 mb-6
              "
            >
              <div>
                <h2 className="text-2xl font-semibold text-gray-800 mb-2">
                  📚 Traitement de plusieurs factures
                </h2>

                <p className="text-gray-600">
                  Sélectionnez une ou plusieurs factures.
                  Chaque sélection traitée crée
                  automatiquement un nouveau lot.
                </p>
              </div>

              <span
                className="
                  shrink-0 px-3 py-1.5 rounded-full
                  bg-purple-50 text-purple-700
                  border border-purple-100
                  text-xs font-semibold
                "
              >
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
              onClick={() =>
                fileInputRef.current?.click()
              }
              onDragOver={handleDragOver}
              onDrop={handleDrop}
              className={`
                border-2 border-dashed rounded-xl
                p-9 text-center cursor-pointer
                transition-all
                ${
                  selectedFiles.length > 0
                    ? (
                        'border-purple-400 ' +
                        'bg-purple-50/20'
                      )
                    : (
                        'border-gray-300 ' +
                        'hover:border-purple-500 ' +
                        'hover:bg-purple-50/10'
                      )
                }
              `}
            >
              <div className="text-4xl mb-2">
                📥
              </div>

              <p className="text-gray-600 font-medium">
                Cliquez ou glissez-déposez
                plusieurs factures
              </p>

              <p className="text-xs text-gray-400 mt-1">
                Images ou PDF — sélection multiple
                disponible
              </p>
            </div>

            {selectedFiles.length > 0 && (
              <div className="mt-5">
                <div
                  className="
                    flex items-center
                    justify-between mb-3
                  "
                >
                  <p className="text-sm font-semibold text-gray-700">
                    {selectedFiles.length}
                    {' '}
                    facture(s) sélectionnée(s)
                  </p>

                  <button
                    type="button"
                    onClick={clearSelection}
                    disabled={processing}
                    className="
                      text-xs text-red-500
                      hover:text-red-700
                      disabled:opacity-40
                    "
                  >
                    Tout retirer
                  </button>
                </div>

                <div
                  className="
                    space-y-2 max-h-52
                    overflow-y-auto pr-1
                  "
                >
                  {selectedFiles.map(
                    (selectedFile, index) => (
                      <div
                        key={`
                          ${selectedFile.name}-
                          ${selectedFile.size}-
                          ${selectedFile.lastModified}
                        `}
                        className="
                          flex justify-between items-center
                          p-3 bg-gray-50 rounded-lg
                          border border-gray-100
                        "
                      >
                        <div className="min-w-0">
                          <p
                            className="
                              text-sm font-medium
                              text-gray-700 truncate
                            "
                          >
                            {selectedFile.name}
                          </p>

                          <p className="text-xs text-gray-400">
                            {(
                              selectedFile.size /
                              1024 /
                              1024
                            ).toFixed(2)}
                            {' '}
                            Mo
                          </p>
                        </div>

                        <button
                          type="button"
                          onClick={() =>
                            removeSelectedFile(index)
                          }
                          disabled={processing}
                          className="
                            text-xs text-red-500
                            hover:text-red-700 ml-3
                            disabled:opacity-40
                          "
                        >
                          Retirer
                        </button>
                      </div>
                    ),
                  )}
                </div>
              </div>
            )}

            {processingError && (
              <div
                className="
                  mt-4 p-3 bg-red-50 text-red-600
                  border border-red-200
                  rounded-md text-sm
                "
              >
                {processingError}
              </div>
            )}

            {processingMessage && (
              <div
                className="
                  mt-4 p-3 bg-green-50 text-green-700
                  border border-green-200
                  rounded-md text-sm
                "
              >
                {processingMessage}
              </div>
            )}

            {selectedFiles.length > 0 && (
              <div
                className="
                  mt-6 flex flex-col sm:flex-row
                  sm:items-center sm:justify-between
                  gap-3
                "
              >
                <p className="text-xs text-gray-400">
                  Un lot sera créé pour ce groupe,
                  même lorsqu'il contient une seule
                  facture.
                </p>

                <button
                  onClick={handleProcessGroup}
                  disabled={processing}
                  className={`
                    px-6 py-2.5 rounded-lg
                    font-medium text-white
                    transition-colors
                    ${
                      processing
                        ? (
                            'bg-purple-400 ' +
                            'cursor-not-allowed'
                          )
                        : (
                            'bg-purple-600 ' +
                            'hover:bg-purple-700 ' +
                            'shadow-sm'
                          )
                    }
                  `}
                >
                  {processing
                    ? (
                        `Traitement ` +
                        `${progress.current}/` +
                        `${progress.total}...`
                      )
                    : (
                        `Lancer l'OCR (` +
                        `${selectedFiles.length} ` +
                        `facture(s)) 🚀`
                      )}
                </button>
              </div>
            )}

            {processing && progress.total > 0 && (
              <div
                className="
                  mt-4 h-2 bg-gray-100
                  rounded-full overflow-hidden
                "
              >
                <div
                  className="
                    h-full bg-purple-500
                    transition-all duration-300
                  "
                  style={{
                    width:
                      (
                        progress.current /
                        progress.total
                      ) *
                        100 +
                      '%',
                  }}
                />
              </div>
            )}

            {groupResults.length > 0 && (
              <div className="mt-7 border-t pt-6">
                <div
                  className="
                    flex flex-col sm:flex-row
                    sm:items-center sm:justify-between
                    gap-3 mb-4
                  "
                >
                  <h3 className="text-lg font-semibold text-gray-800">
                    Résultat

                    {currentLot && (
                      <span className="text-purple-600">
                        {' '}
                        — {currentLot.reference}
                      </span>
                    )}
                  </h3>

                  <button
                    onClick={handleExportGroupExcel}
                    disabled={
                      !groupResults.some(
                        (result) =>
                          result.status === 'done',
                      )
                    }
                    className="
                      bg-emerald-700
                      hover:bg-emerald-800
                      text-white px-4 py-2
                      rounded-lg text-sm font-medium
                      shadow-sm transition-colors
                      disabled:opacity-40
                    "
                  >
                    📊 Exporter le lot en Excel
                  </button>
                </div>

                <div className="space-y-2">
                  {groupResults.map(
                    (result, index) => (
                      <div
                        key={
                          result.id ||
                          `${result.filename}-${index}`
                        }
                        className={`
                          flex flex-col sm:flex-row
                          sm:items-center
                          sm:justify-between
                          gap-3 p-3 rounded-lg border
                          ${
                            result.status === 'done'
                              ? (
                                  'border-green-100 ' +
                                  'bg-green-50/30'
                                )
                              : (
                                  'border-red-100 ' +
                                  'bg-red-50/30'
                                )
                          }
                        `}
                      >
                        <div className="min-w-0">
                          <p
                            className="
                              text-sm font-medium
                              text-gray-700 truncate
                            "
                          >
                            {result.filename}
                          </p>

                          {result.status === 'done' ? (
                            <p className="text-xs text-gray-400">
                              {
                                result
                                  .structured_data
                                  ?.provider
                              }
                              {' '}
                              —
                              {' '}
                              {
                                result
                                  .structured_data
                                  ?.total_ttc
                              }
                            </p>
                          ) : (
                            <p className="text-xs text-red-500">
                              {result.error_message}
                            </p>
                          )}
                        </div>

                        <div
                          className="
                            flex items-center gap-2
                            shrink-0
                          "
                        >
                          {result.status === 'done' && (
                            <button
                              type="button"
                              onClick={() =>
                                openDocument(result)
                              }
                              className="
                                px-3 py-1.5 rounded-md
                                text-xs font-semibold
                                bg-blue-50 text-blue-700
                                hover:bg-blue-100
                                border border-blue-100
                              "
                            >
                              {canEditFields
                                ? '✏️ Modifier'
                                : '👁️ Consulter'}
                            </button>
                          )}

                          <span
                            className={`
                              text-xs font-medium
                              px-2 py-1 rounded-full
                              ${
                                result.status === 'done'
                                  ? (
                                      'bg-green-100 ' +
                                      'text-green-700'
                                    )
                                  : (
                                      'bg-red-100 ' +
                                      'text-red-700'
                                    )
                              }
                            `}
                          >
                            {result.status === 'done'
                              ? '✓ Traité'
                              : '✗ Échec'}
                          </span>
                        </div>
                      </div>
                    ),
                  )}
                </div>
              </div>
            )}
          </section>

          {extractedText && structuredData && (
            <section
              className="
                bg-white rounded-xl shadow-sm
                border border-gray-200
                overflow-hidden
              "
            >
              <div
                className="
                  border-b bg-gray-50
                  px-6 py-3
                  flex flex-col sm:flex-row
                  sm:items-center sm:justify-between
                  gap-3
                "
              >
                <div>
                  <p
                    className="
                      text-xs text-gray-400
                      uppercase font-semibold
                    "
                  >
                    Facture sélectionnée
                  </p>

                  <h3
                    className="
                      font-semibold text-gray-800
                      truncate
                    "
                  >
                    {currentFilename}
                  </h3>
                </div>

                <span
                  className={`
                    px-3 py-1 rounded-full
                    text-xs font-medium border
                    self-start sm:self-auto
                    ${
                      isValidated
                        ? (
                            'bg-green-100 ' +
                            'text-green-700 ' +
                            'border-green-200'
                          )
                        : (
                            'bg-amber-100 ' +
                            'text-amber-700 ' +
                            'border-amber-200'
                          )
                    }
                  `}
                >
                  {isValidated
                    ? '✓ Validée'
                    : '⏳ En attente de validation'}
                </span>
              </div>

              <div
                className="
                  px-6 pt-4 border-b flex gap-4
                "
              >
                <button
                  onClick={() =>
                    setActiveTab('structured')
                  }
                  className={`
                    pb-3 text-sm font-medium
                    border-b-2 transition-colors
                    ${
                      activeTab === 'structured'
                        ? (
                            'border-blue-600 ' +
                            'text-blue-600'
                          )
                        : (
                            'border-transparent ' +
                            'text-gray-500 ' +
                            'hover:text-gray-700'
                          )
                    }
                  `}
                >
                  📈 Données extraites
                </button>

                <button
                  onClick={() =>
                    setActiveTab('raw')
                  }
                  className={`
                    pb-3 text-sm font-medium
                    border-b-2 transition-colors
                    ${
                      activeTab === 'raw'
                        ? (
                            'border-blue-600 ' +
                            'text-blue-600'
                          )
                        : (
                            'border-transparent ' +
                            'text-gray-500 ' +
                            'hover:text-gray-700'
                          )
                    }
                  `}
                >
                  📝 Texte brut OCR
                </button>
              </div>

              <div className="p-6">
                {editorError && (
                  <div
                    className="
                      mb-4 p-3 bg-red-50
                      text-red-600
                      border border-red-200
                      rounded-md text-sm
                    "
                  >
                    {editorError}
                  </div>
                )}

                {editorMessage && (
                  <div
                    className="
                      mb-4 p-3 bg-green-50
                      text-green-700
                      border border-green-200
                      rounded-md text-sm
                    "
                  >
                    {editorMessage}
                  </div>
                )}

                {activeTab === 'structured' && (
                  <div className="space-y-4">
                    {!canEditFields && (
                      <p className="text-xs text-gray-400 italic">
                        Les données sont en lecture seule.
                        Seul un comptable ou un
                        administrateur peut les modifier
                        et les valider.
                      </p>
                    )}

                    <div
                      className="
                        grid grid-cols-1
                        sm:grid-cols-3 gap-4
                      "
                    >
                      <div>
                        <label
                          className="
                            text-xs font-semibold
                            text-gray-400 uppercase
                          "
                        >
                          Fournisseur
                        </label>

                        <input
                          type="text"
                          readOnly={!canEditFields}
                          className={inputClassName}
                          value={structuredData.provider}
                          onChange={(event) =>
                            updateStructuredField(
                              'provider',
                              event.target.value,
                            )
                          }
                        />
                      </div>

                      <div>
                        <label
                          className="
                            text-xs font-semibold
                            text-gray-400 uppercase
                          "
                        >
                          Client
                        </label>

                        <input
                          type="text"
                          readOnly={!canEditFields}
                          className={inputClassName}
                          value={structuredData.client}
                          onChange={(event) =>
                            updateStructuredField(
                              'client',
                              event.target.value,
                            )
                          }
                        />
                      </div>

                      <div>
                        <label
                          className="
                            text-xs font-semibold
                            text-gray-400 uppercase
                          "
                        >
                          Date facture
                        </label>

                        <input
                          type="text"
                          readOnly={!canEditFields}
                          className={inputClassName}
                          value={structuredData.date}
                          onChange={(event) =>
                            updateStructuredField(
                              'date',
                              event.target.value,
                            )
                          }
                        />
                      </div>
                    </div>

                    <div
                      className="
                        grid grid-cols-1
                        sm:grid-cols-3 gap-4
                      "
                    >
                      <div>
                        <label
                          className="
                            text-xs font-semibold
                            text-gray-400 uppercase
                          "
                        >
                          ICE
                        </label>

                        <input
                          type="text"
                          readOnly={!canEditFields}
                          className={inputClassName}
                          value={structuredData.ice}
                          onChange={(event) =>
                            updateStructuredField(
                              'ice',
                              event.target.value,
                            )
                          }
                        />
                      </div>

                      <div>
                        <label
                          className="
                            text-xs font-semibold
                            text-gray-400 uppercase
                          "
                        >
                          IF
                        </label>

                        <input
                          type="text"
                          readOnly={!canEditFields}
                          className={inputClassName}
                          value={
                            structuredData.if_number
                          }
                          onChange={(event) =>
                            updateStructuredField(
                              'if_number',
                              event.target.value,
                            )
                          }
                        />
                      </div>

                      <div>
                        <label
                          className="
                            text-xs font-semibold
                            text-gray-400 uppercase
                          "
                        >
                          RC
                        </label>

                        <input
                          type="text"
                          readOnly={!canEditFields}
                          className={inputClassName}
                          value={structuredData.rc}
                          onChange={(event) =>
                            updateStructuredField(
                              'rc',
                              event.target.value,
                            )
                          }
                        />
                      </div>
                    </div>

                    <div
                      className="
                        grid grid-cols-1
                        sm:grid-cols-3 gap-4 pt-2
                      "
                    >
                      <div>
                        <label
                          className="
                            text-xs font-semibold
                            text-gray-400 uppercase
                          "
                        >
                          Total HT
                        </label>

                        <input
                          type="text"
                          readOnly={!canEditFields}
                          className={inputClassName}
                          value={
                            structuredData.total_ht
                          }
                          onChange={(event) =>
                            updateStructuredField(
                              'total_ht',
                              event.target.value,
                            )
                          }
                        />
                      </div>

                      <div>
                        <label
                          className="
                            text-xs font-semibold
                            text-gray-400 uppercase
                          "
                        >
                          TVA
                        </label>

                        <input
                          type="text"
                          readOnly={!canEditFields}
                          className={inputClassName}
                          value={structuredData.tva}
                          onChange={(event) =>
                            updateStructuredField(
                              'tva',
                              event.target.value,
                            )
                          }
                        />
                      </div>

                      <div>
                        <label
                          className="
                            text-xs font-semibold
                            text-gray-400 uppercase
                          "
                        >
                          Total TTC
                        </label>

                        <input
                          type="text"
                          readOnly={!canEditFields}
                          className={`
                            ${inputClassName}
                            ${
                              canEditFields
                                ? (
                                    'text-green-700 ' +
                                    'bg-green-50/50 ' +
                                    'border-green-200'
                                  )
                                : ''
                            }
                          `}
                          value={
                            structuredData.total_ttc
                          }
                          onChange={(event) =>
                            updateStructuredField(
                              'total_ttc',
                              event.target.value,
                            )
                          }
                        />
                      </div>
                    </div>

                    <div
                      className="
                        flex flex-col sm:flex-row
                        sm:items-center
                        sm:justify-between
                        gap-3 pt-4 border-t mt-4
                      "
                    >
                      <div className="flex gap-2">
                        <button
                          onClick={handleExportJSON}
                          className="
                            bg-gray-800
                            hover:bg-gray-900
                            text-white px-4 py-2
                            rounded-lg text-sm
                            font-medium shadow-sm
                            transition-colors
                          "
                        >
                          📥 JSON
                        </button>

                        <button
                          onClick={handleExportExcel}
                          className="
                            bg-emerald-700
                            hover:bg-emerald-800
                            text-white px-4 py-2
                            rounded-lg text-sm
                            font-medium shadow-sm
                            transition-colors
                          "
                        >
                          📊 Excel
                        </button>
                      </div>

                      {canValidate && currentDocId && (
                        <button
                          onClick={handleValidate}
                          disabled={validating}
                          className={`
                            px-5 py-2 rounded-lg
                            font-medium shadow-sm
                            transition-colors text-white
                            ${
                              validating
                                ? (
                                    'bg-green-400 ' +
                                    'cursor-not-allowed'
                                  )
                                : isValidated
                                  ? (
                                      'bg-emerald-700 ' +
                                      'hover:bg-emerald-800'
                                    )
                                  : (
                                      'bg-green-600 ' +
                                      'hover:bg-green-700'
                                    )
                            }
                          `}
                        >
                          {validating
                            ? 'Enregistrement...'
                            : isValidated
                              ? (
                                  '🔄 Enregistrer ' +
                                  'les modifications'
                                )
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
                    rows={12}
                    className="
                      w-full p-4
                      border border-gray-300
                      rounded-lg bg-gray-50
                      text-gray-700 font-mono
                      text-sm focus:outline-none
                    "
                  />
                )}
              </div>
            </section>
          )}
        </div>

        <aside
          className="
            bg-white p-6 rounded-xl
            shadow-sm border border-gray-200
            h-[680px] flex flex-col
          "
        >
          <h3
            className="
              text-lg font-semibold
              text-gray-800 mb-2
              flex items-center gap-2
            "
          >
            <span>📂</span>
            Historique des analyses
          </h3>

          <div className="mb-4">
            <input
              type="text"
              placeholder="🔍 Rechercher une facture..."
              value={searchQuery}
              onChange={(event) =>
                setSearchQuery(event.target.value)
              }
              className="
                w-full px-3 py-2 text-sm
                border border-gray-300
                rounded-lg focus:outline-none
                focus:ring-2
                focus:ring-blue-500/20
              "
            />
          </div>

          <div
            className="
              flex-1 overflow-y-auto
              space-y-3 pr-1
            "
          >
            {filteredHistory.length === 0 ? (
              <p
                className="
                  text-sm text-gray-400 italic
                  text-center mt-10
                "
              >
                Aucun document trouvé.
              </p>
            ) : (
              filteredHistory.map((document) => (
                <button
                  type="button"
                  key={document.id}
                  onClick={() =>
                    handleSelectHistory(document)
                  }
                  className={`
                    w-full text-left p-3
                    border rounded-xl
                    hover:bg-blue-50/40
                    hover:border-blue-200
                    cursor-pointer
                    transition-all shadow-sm
                    ${
                      currentDocId === document.id
                        ? (
                            'border-blue-300 ' +
                            'bg-blue-50/40'
                          )
                        : 'border-gray-100'
                    }
                  `}
                >
                  <div
                    className="
                      flex justify-between
                      items-start gap-2
                    "
                  >
                    <p
                      className="
                        text-sm font-semibold
                        text-gray-700 truncate
                      "
                    >
                      {document.filename}
                    </p>

                    <span
                      className={`
                        shrink-0 px-2 py-0.5
                        rounded-full text-[10px]
                        font-medium border
                        ${
                          document.is_validated
                            ? (
                                'bg-green-100 ' +
                                'text-green-700 ' +
                                'border-green-200'
                              )
                            : (
                                'bg-amber-100 ' +
                                'text-amber-700 ' +
                                'border-amber-200'
                              )
                        }
                      `}
                    >
                      {document.is_validated
                        ? 'Validée'
                        : 'En attente'}
                    </span>
                  </div>

                  <div
                    className="
                      flex items-center
                      justify-between mt-1
                      gap-2
                    "
                  >
                    <span className="text-xs text-gray-400">
                      {new Date(
                        document.created_at,
                      ).toLocaleDateString('fr-FR')}
                    </span>

                    {document.lot_id && (
                      <span
                        className="
                          text-[10px]
                          text-purple-600
                          bg-purple-50
                          px-2 py-0.5
                          rounded-full
                        "
                      >
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