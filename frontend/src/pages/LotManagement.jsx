import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api';
import NotificationBell from '../components/NotificationBell';

const toEditableDocument = (document) => ({
  id: document.id,
  filename: document.filename,
  provider: document.provider || '',
  client: document.client || '',
  date: document.invoice_date || '',
  ice: document.ice || '',
  if_number: document.if_number || '',
  rc: document.rc || '',
  total_ht: document.total_ht || '',
  tva: document.tva || '',
  total_ttc: document.total_ttc || '',
});

function LotManagement() {
  const navigate = useNavigate();

  const [lots, setLots] = useState([]);
  const [selectedLot, setSelectedLot] = useState(null);
  const [unassignedDocs, setUnassignedDocs] = useState([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  const [newLotRef, setNewLotRef] = useState('');
  const [creating, setCreating] = useState(false);

  const [editingDocument, setEditingDocument] =
    useState(null);

  const [savingDocument, setSavingDocument] =
    useState(false);

  useEffect(() => {
    fetchLots();
  }, []);

  const fetchLots = async () => {
    setLoading(true);
    setError('');

    try {
      const response = await api.get('/lots');
      setLots(response.data);
    } catch (requestError) {
      console.error(requestError);

      setError(
        'Impossible de charger la liste des lots.',
      );
    } finally {
      setLoading(false);
    }
  };

  const fetchLotDetail = async (lotId) => {
    setError('');

    try {
      const response = await api.get(
        `/lots/${lotId}`,
      );

      setSelectedLot(response.data);

      return response.data;
    } catch (requestError) {
      console.error(requestError);

      setError(
        'Impossible de charger le détail du lot.',
      );

      return null;
    }
  };

  const fetchUnassignedDocs = async () => {
    try {
      const response = await api.get(
        '/ocr/history',
      );

      setUnassignedDocs(
        response.data.filter(
          (document) => !document.lot_id,
        ),
      );
    } catch (requestError) {
      console.error(
        (
          'Erreur lors de la récupération ' +
          'des documents :'
        ),
        requestError,
      );
    }
  };

  const handleCreateLot = async () => {
    setCreating(true);
    setError('');
    setSuccessMessage('');

    try {
      await api.post('/lots', {
        reference:
          newLotRef.trim() || null,
      });

      setNewLotRef('');

      setSuccessMessage(
        'Le lot a été créé avec succès.',
      );

      await fetchLots();
    } catch (requestError) {
      setError(
        requestError.response?.data?.detail ||
          'Erreur lors de la création du lot.',
      );
    } finally {
      setCreating(false);
    }
  };

  const handleSelectLot = async (lot) => {
    setEditingDocument(null);
    setSuccessMessage('');

    await Promise.all([
      fetchLotDetail(lot.id),
      fetchUnassignedDocs(),
    ]);
  };

  const handleAssignDoc = async (documentId) => {
    if (!selectedLot) {
      return;
    }

    setError('');
    setSuccessMessage('');

    try {
      await api.put(
        `/ocr/documents/${documentId}/lot`,
        {
          lot_id: selectedLot.id,
        },
      );

      await Promise.all([
        fetchLotDetail(selectedLot.id),
        fetchUnassignedDocs(),
        fetchLots(),
      ]);

      setSuccessMessage(
        'La facture a été ajoutée au lot.',
      );
    } catch (requestError) {
      setError(
        requestError.response?.data?.detail ||
          (
            "Erreur lors de l'assignation " +
            'du document.'
          ),
      );
    }
  };

  const handleRemoveDoc = async (documentId) => {
    if (!selectedLot) {
      return;
    }

    setError('');
    setSuccessMessage('');

    try {
      await api.put(
        `/ocr/documents/${documentId}/lot`,
        {
          lot_id: null,
        },
      );

      if (editingDocument?.id === documentId) {
        setEditingDocument(null);
      }

      await Promise.all([
        fetchLotDetail(selectedLot.id),
        fetchUnassignedDocs(),
        fetchLots(),
      ]);

      setSuccessMessage(
        'La facture a été retirée du lot.',
      );
    } catch (requestError) {
      setError(
        requestError.response?.data?.detail ||
          (
            'Erreur lors du retrait ' +
            'du document.'
          ),
      );
    }
  };

  const handleDeleteLot = async (
    lotId,
    reference,
  ) => {
    const confirmed = window.confirm(
      (
        `Supprimer le lot ${reference} ? ` +
        'Les documents seront détachés, ' +
        'mais ils ne seront pas supprimés.'
      ),
    );

    if (!confirmed) {
      return;
    }

    setError('');
    setSuccessMessage('');

    try {
      await api.delete(`/lots/${lotId}`);

      if (selectedLot?.id === lotId) {
        setSelectedLot(null);
        setEditingDocument(null);
      }

      setSuccessMessage(
        `Le lot ${reference} a été supprimé.`,
      );

      await fetchLots();
    } catch (requestError) {
      setError(
        requestError.response?.data?.detail ||
          (
            'Erreur lors de la suppression ' +
            'du lot.'
          ),
      );
    }
  };

  const handleEditDocument = (document) => {
    setEditingDocument(
      toEditableDocument(document),
    );

    setError('');
    setSuccessMessage('');
  };

  const updateEditingField = (
    field,
    value,
  ) => {
    setEditingDocument((document) => ({
      ...document,
      [field]: value,
    }));
  };

  const handleSaveDocument = async () => {
    if (!editingDocument || !selectedLot) {
      return;
    }

    setSavingDocument(true);
    setError('');
    setSuccessMessage('');

    try {
      await api.put(
        (
          `/ocr/documents/` +
          `${editingDocument.id}/validate`
        ),
        {
          provider: editingDocument.provider,
          client: editingDocument.client,
          date: editingDocument.date,
          ice: editingDocument.ice,
          if_number:
            editingDocument.if_number,
          rc: editingDocument.rc,
          total_ht:
            editingDocument.total_ht,
          tva: editingDocument.tva,
          total_ttc:
            editingDocument.total_ttc,
        },
      );

      const refreshedLot =
        await fetchLotDetail(selectedLot.id);

      if (refreshedLot) {
        const refreshedDocument =
          refreshedLot.documents.find(
            (document) =>
              document.id === editingDocument.id,
          );

        if (refreshedDocument) {
          setEditingDocument(
            toEditableDocument(
              refreshedDocument,
            ),
          );
        }
      }

      setSuccessMessage(
        (
          `Les données de ` +
          `${editingDocument.filename} ` +
          'ont été enregistrées.'
        ),
      );
    } catch (requestError) {
      setError(
        requestError.response?.data?.detail ||
          (
            'Erreur lors de la modification ' +
            'de la facture.'
          ),
      );
    } finally {
      setSavingDocument(false);
    }
  };

  const editFields = [
    ['provider', 'Fournisseur'],
    ['client', 'Client'],
    ['date', 'Date facture'],
    ['ice', 'ICE'],
    ['if_number', 'IF'],
    ['rc', 'RC'],
    ['total_ht', 'Total HT'],
    ['tva', 'TVA'],
    ['total_ttc', 'Total TTC'],
  ];

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col font-sans">
      <nav className="bg-white shadow-sm border-b">
        <div
          className="
            max-w-7xl mx-auto
            px-4 sm:px-6 lg:px-8
          "
        >
          <div
            className="
              flex justify-between
              h-16 items-center
            "
          >
            <h1 className="text-xl font-bold text-blue-600">
              OCR Accounting Platform 🚀
            </h1>
           <div className="flex items-center gap-3">
            <NotificationBell />
            <button
              onClick={() =>
                navigate('/dashboard')
              }
              className="
                px-4 py-2 text-sm font-medium
                text-gray-700 bg-gray-100
                hover:bg-gray-200 rounded-md
                transition-colors
              "
            >
              ← Retour au tableau de bord
            </button>
          </div>
       </div>
    </div>
  </nav>

      <main
        className="
          max-w-6xl w-full mx-auto
          py-10 px-4 sm:px-6 lg:px-8
          grid grid-cols-1 md:grid-cols-3
          gap-6
        "
      >
        <div className="md:col-span-1 space-y-4">
          <div
            className="
              bg-white rounded-xl shadow-sm
              border border-gray-200 p-5
            "
          >
            <h2 className="text-lg font-semibold text-gray-800 mb-3">
              Nouveau lot
            </h2>

            <input
              type="text"
              placeholder="Référence facultative"
              value={newLotRef}
              onChange={(event) =>
                setNewLotRef(event.target.value)
              }
              className="
                w-full px-3 py-2
                border border-gray-300
                rounded-md text-sm mb-3
                focus:outline-none
                focus:ring-2
                focus:ring-blue-500/20
              "
            />

            <button
              onClick={handleCreateLot}
              disabled={creating}
              className="
                w-full py-2 bg-blue-600
                hover:bg-blue-700
                text-white rounded-md
                text-sm font-medium
                disabled:opacity-50
              "
            >
              {creating
                ? 'Création...'
                : '+ Créer un lot'}
            </button>
          </div>

          <div
            className="
              bg-white rounded-xl shadow-sm
              border border-gray-200 p-5
            "
          >
            <h2 className="text-lg font-semibold text-gray-800 mb-3">
              Lots existants
            </h2>

            {loading ? (
              <p className="text-sm text-gray-400">
                Chargement...
              </p>
            ) : lots.length === 0 ? (
              <p className="text-sm text-gray-400 italic">
                Aucun lot pour le moment.
              </p>
            ) : (
              <div
                className="
                  space-y-2 max-h-[560px]
                  overflow-y-auto pr-1
                "
              >
                {lots.map((lot) => (
                  <div
                    key={lot.id}
                    onClick={() =>
                      handleSelectLot(lot)
                    }
                    className={`
                      p-3 rounded-lg border
                      cursor-pointer
                      transition-colors
                      ${
                        selectedLot?.id === lot.id
                          ? (
                              'border-blue-400 ' +
                              'bg-blue-50/50'
                            )
                          : (
                              'border-gray-200 ' +
                              'hover:bg-gray-50'
                            )
                      }
                    `}
                  >
                    <div
                      className="
                        flex justify-between
                        items-center gap-2
                      "
                    >
                      <span
                        className="
                          font-medium text-gray-700
                          text-sm truncate
                        "
                      >
                        {lot.reference}
                      </span>

                      <span
                        className="
                          text-xs text-gray-400
                          shrink-0
                        "
                      >
                        {lot.document_count}
                        {' '}
                        facture(s)
                      </span>
                    </div>

                    <div
                      className="
                        flex justify-between
                        items-center mt-1
                      "
                    >
                      <span className="text-xs text-gray-400">
                        {new Date(
                          lot.created_at,
                        ).toLocaleDateString(
                          'fr-FR',
                        )}
                      </span>

                      <button
                        onClick={(event) => {
                          event.stopPropagation();

                          handleDeleteLot(
                            lot.id,
                            lot.reference,
                          );
                        }}
                        className="
                          text-xs text-red-500
                          hover:text-red-700
                        "
                      >
                        Supprimer
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="md:col-span-2 space-y-4">
          {error && (
            <div
              className="
                p-3 bg-red-50 text-red-600
                border border-red-200
                rounded-md text-sm
              "
            >
              {error}
            </div>
          )}

          {successMessage && (
            <div
              className="
                p-3 bg-green-50 text-green-700
                border border-green-200
                rounded-md text-sm
              "
            >
              {successMessage}
            </div>
          )}

          {!selectedLot ? (
            <div
              className="
                bg-white rounded-xl shadow-sm
                border border-gray-200 p-10
                text-center text-gray-400
              "
            >
              Sélectionnez un lot pour consulter et
              modifier ses factures.
            </div>
          ) : (
            <>
              <div
                className="
                  bg-white rounded-xl shadow-sm
                  border border-gray-200 p-6
                "
              >
                <h2
                  className="
                    text-xl font-semibold
                    text-gray-800 mb-4
                  "
                >
                  📦 {selectedLot.reference}
                  {' '}
                  —
                  {' '}
                  {selectedLot.documents.length}
                  {' '}
                  facture(s)
                </h2>

                {selectedLot.documents.length === 0 ? (
                  <p className="text-sm text-gray-400 italic">
                    Aucune facture dans ce lot.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {selectedLot.documents.map(
                      (document) => (
                        <div
                          key={document.id}
                          className={`
                            flex flex-col sm:flex-row
                            sm:items-center
                            sm:justify-between
                            gap-3 p-3 border
                            rounded-lg
                            ${
                              editingDocument?.id ===
                              document.id
                                ? (
                                    'border-blue-300 ' +
                                    'bg-blue-50/30'
                                  )
                                : 'border-gray-100'
                            }
                          `}
                        >
                          <div className="min-w-0">
                            <div
                              className="
                                flex items-center
                                gap-2
                              "
                            >
                              <p
                                className="
                                  text-sm font-medium
                                  text-gray-700
                                  truncate
                                "
                              >
                                {document.filename}
                              </p>

                              <span
                                className={`
                                  text-[10px]
                                  px-2 py-0.5
                                  rounded-full
                                  ${
                                    document.is_validated
                                      ? (
                                          'bg-green-100 ' +
                                          'text-green-700'
                                        )
                                      : (
                                          'bg-amber-100 ' +
                                          'text-amber-700'
                                        )
                                  }
                                `}
                              >
                                {document.is_validated
                                  ? 'Validée'
                                  : 'En attente'}
                              </span>
                            </div>

                            <p className="text-xs text-gray-400">
                              {
                                document.provider ||
                                'Fournisseur inconnu'
                              }
                              {' '}
                              —
                              {' '}
                              {
                                document.total_ttc ||
                                '0.00'
                              }
                            </p>
                          </div>

                          <div
                            className="
                              flex items-center gap-3
                              shrink-0
                            "
                          >
                            <button
                              onClick={() =>
                                handleEditDocument(
                                  document,
                                )
                              }
                              className="
                                text-xs text-blue-600
                                hover:text-blue-800
                                font-medium
                              "
                            >
                              ✏️ Modifier
                            </button>

                            <button
                              onClick={() =>
                                handleRemoveDoc(
                                  document.id,
                                )
                              }
                              className="
                                text-xs text-red-500
                                hover:text-red-700
                              "
                            >
                              Retirer du lot
                            </button>
                          </div>
                        </div>
                      ),
                    )}
                  </div>
                )}
              </div>

              {editingDocument && (
                <div
                  className="
                    bg-white rounded-xl shadow-sm
                    border border-blue-200 p-6
                  "
                >
                  <div
                    className="
                      flex items-start
                      justify-between gap-3 mb-5
                    "
                  >
                    <div>
                      <p
                        className="
                          text-xs font-semibold
                          text-blue-500 uppercase
                        "
                      >
                        Modification de la facture
                      </p>

                      <h3
                        className="
                          text-lg font-semibold
                          text-gray-800
                        "
                      >
                        {editingDocument.filename}
                      </h3>
                    </div>

                    <button
                      onClick={() =>
                        setEditingDocument(null)
                      }
                      className="
                        text-sm text-gray-400
                        hover:text-gray-600
                      "
                    >
                      Fermer ✕
                    </button>
                  </div>

                  <div
                    className="
                      grid grid-cols-1
                      sm:grid-cols-3 gap-4
                    "
                  >
                    {editFields.map(
                      ([field, label]) => (
                        <div key={field}>
                          <label
                            className="
                              text-xs font-semibold
                              text-gray-400 uppercase
                            "
                          >
                            {label}
                          </label>

                          <input
                            type="text"
                            value={
                              editingDocument[field]
                            }
                            onChange={(event) =>
                              updateEditingField(
                                field,
                                event.target.value,
                              )
                            }
                            className={`
                              w-full mt-1 px-3 py-2
                              border rounded-lg
                              text-sm focus:outline-none
                              focus:ring-2
                              focus:ring-blue-500/20
                              ${
                                field === 'total_ttc'
                                  ? (
                                      'border-green-200 ' +
                                      'bg-green-50/30 ' +
                                      'text-green-700 ' +
                                      'font-semibold'
                                    )
                                  : 'border-gray-300'
                              }
                            `}
                          />
                        </div>
                      ),
                    )}
                  </div>

                  <div
                    className="
                      flex justify-end mt-5
                      pt-4 border-t
                    "
                  >
                    <button
                      onClick={handleSaveDocument}
                      disabled={savingDocument}
                      className="
                        px-5 py-2 bg-green-600
                        hover:bg-green-700
                        text-white rounded-lg
                        text-sm font-medium
                        disabled:opacity-50
                      "
                    >
                      {savingDocument
                        ? 'Enregistrement...'
                        : (
                            '✓ Enregistrer ' +
                            'les modifications'
                          )}
                    </button>
                  </div>
                </div>
              )}

              <div
                className="
                  bg-white rounded-xl shadow-sm
                  border border-gray-200 p-6
                "
              >
                <h3
                  className="
                    text-lg font-semibold
                    text-gray-800 mb-4
                  "
                >
                  Factures non assignées
                </h3>

                {unassignedDocs.length === 0 ? (
                  <p className="text-sm text-gray-400 italic">
                    Aucune facture disponible à
                    assigner.
                  </p>
                ) : (
                  <div
                    className="
                      space-y-2 max-h-72
                      overflow-y-auto pr-1
                    "
                  >
                    {unassignedDocs.map(
                      (document) => (
                        <div
                          key={document.id}
                          className="
                            flex flex-col sm:flex-row
                            sm:items-center
                            sm:justify-between
                            gap-3 p-3
                            border border-gray-100
                            rounded-lg
                          "
                        >
                          <div className="min-w-0">
                            <p
                              className="
                                text-sm font-medium
                                text-gray-700 truncate
                              "
                            >
                              {document.filename}
                            </p>

                            <p className="text-xs text-gray-400">
                              {
                                document.provider ||
                                'Fournisseur inconnu'
                              }
                              {' '}
                              —
                              {' '}
                              {
                                document.total_ttc ||
                                '0.00'
                              }
                            </p>
                          </div>

                          <button
                            onClick={() =>
                              handleAssignDoc(
                                document.id,
                              )
                            }
                            className="
                              text-xs text-blue-600
                              hover:text-blue-800
                              font-medium shrink-0
                            "
                          >
                            + Ajouter au lot
                          </button>
                        </div>
                      ),
                    )}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  );
}

export default LotManagement;