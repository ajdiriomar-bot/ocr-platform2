import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api';

function LotManagement() {
  const navigate = useNavigate();
  const [lots, setLots] = useState([]);
  const [selectedLot, setSelectedLot] = useState(null);
  const [unassignedDocs, setUnassignedDocs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [newLotRef, setNewLotRef] = useState('');
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    fetchLots();
  }, []);

  const fetchLots = async () => {
    setLoading(true);
    setError('');
    try {
      const response = await api.get('/lots');
      setLots(response.data);
    } catch (err) {
      setError("Impossible de charger la liste des lots.");
    } finally {
      setLoading(false);
    }
  };

  const fetchLotDetail = async (lotId) => {
    setError('');
    try {
      const response = await api.get(`/lots/${lotId}`);
      setSelectedLot(response.data);
    } catch (err) {
      setError("Impossible de charger le détail du lot.");
    }
  };

  const fetchUnassignedDocs = async () => {
    try {
      const response = await api.get('/ocr/history');
      setUnassignedDocs(response.data.filter(doc => !doc.lot_id));
    } catch (err) {
      console.error("Erreur lors de la récupération des documents :", err);
    }
  };

  const handleCreateLot = async () => {
    setCreating(true);
    setError('');
    try {
      await api.post('/lots', { reference: newLotRef || null });
      setNewLotRef('');
      fetchLots();
    } catch (err) {
      setError(err.response?.data?.detail || "Erreur lors de la création du lot.");
    } finally {
      setCreating(false);
    }
  };

  const handleSelectLot = (lot) => {
    fetchLotDetail(lot.id);
    fetchUnassignedDocs();
  };

  const handleAssignDoc = async (docId) => {
    if (!selectedLot) return;
    setError('');
    try {
      await api.put(`/ocr/documents/${docId}/lot`, { lot_id: selectedLot.id });
      fetchLotDetail(selectedLot.id);
      fetchUnassignedDocs();
      fetchLots();
    } catch (err) {
      setError(err.response?.data?.detail || "Erreur lors de l'assignation du document.");
    }
  };

  const handleRemoveDoc = async (docId) => {
    setError('');
    try {
      await api.put(`/ocr/documents/${docId}/lot`, { lot_id: null });
      fetchLotDetail(selectedLot.id);
      fetchUnassignedDocs();
      fetchLots();
    } catch (err) {
      setError(err.response?.data?.detail || "Erreur lors du retrait du document.");
    }
  };

  const handleDeleteLot = async (lotId, reference) => {
    if (!window.confirm(`Supprimer le lot ${reference} ? Les documents seront détachés, pas supprimés.`)) return;
    setError('');
    try {
      await api.delete(`/lots/${lotId}`);
      if (selectedLot?.id === lotId) setSelectedLot(null);
      fetchLots();
    } catch (err) {
      setError(err.response?.data?.detail || "Erreur lors de la suppression du lot.");
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col font-sans">
      <nav className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16 items-center">
            <h1 className="text-xl font-bold text-blue-600">OCR Accounting Platform 🚀</h1>
            <button
              onClick={() => navigate('/dashboard')}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-md transition-colors"
            >
              ← Retour au tableau de bord
            </button>
          </div>
        </div>
      </nav>

      <main className="max-w-6xl w-full mx-auto py-10 px-4 sm:px-6 lg:px-8 grid grid-cols-1 md:grid-cols-3 gap-6">

        {/* Colonne gauche : liste des lots */}
        <div className="md:col-span-1 space-y-4">
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
            <h2 className="text-lg font-semibold text-gray-800 mb-3">Nouveau lot</h2>
            <input
              type="text"
              placeholder="Référence (optionnel, auto si vide)"
              value={newLotRef}
              onChange={(e) => setNewLotRef(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm mb-3 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            />
            <button
              onClick={handleCreateLot}
              disabled={creating}
              className="w-full py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md text-sm font-medium disabled:opacity-50"
            >
              {creating ? "Création..." : "+ Créer un lot"}
            </button>
          </div>

          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
            <h2 className="text-lg font-semibold text-gray-800 mb-3">Lots existants</h2>
            {loading ? (
              <p className="text-sm text-gray-400">Chargement...</p>
            ) : lots.length === 0 ? (
              <p className="text-sm text-gray-400 italic">Aucun lot pour le moment.</p>
            ) : (
              <div className="space-y-2">
                {lots.map((lot) => (
                  <div
                    key={lot.id}
                    onClick={() => handleSelectLot(lot)}
                    className={`p-3 rounded-lg border cursor-pointer transition-colors ${
                      selectedLot?.id === lot.id ? 'border-blue-400 bg-blue-50/50' : 'border-gray-200 hover:bg-gray-50'
                    }`}
                  >
                    <div className="flex justify-between items-center">
                      <span className="font-medium text-gray-700 text-sm">{lot.reference}</span>
                      <span className="text-xs text-gray-400">{lot.document_count} doc.</span>
                    </div>
                    <div className="flex justify-between items-center mt-1">
                      <span className="text-xs text-gray-400">
                        {new Date(lot.created_at).toLocaleDateString('fr-FR')}
                      </span>
                      <button
                        onClick={(e) => { e.stopPropagation(); handleDeleteLot(lot.id, lot.reference); }}
                        className="text-xs text-red-500 hover:text-red-700"
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

        {/* Colonne droite : détail du lot sélectionné */}
        <div className="md:col-span-2">
          {error && (
            <div className="mb-4 p-3 bg-red-50 text-red-600 border border-red-200 rounded-md text-sm">
              {error}
            </div>
          )}

          {!selectedLot ? (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-10 text-center text-gray-400">
              Sélectionnez un lot pour voir son contenu, ou créez-en un nouveau.
            </div>
          ) : (
            <div className="space-y-6">
              <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                <h2 className="text-xl font-semibold text-gray-800 mb-4">
                  📦 {selectedLot.reference} — {selectedLot.documents.length} document(s)
                </h2>

                {selectedLot.documents.length === 0 ? (
                  <p className="text-sm text-gray-400 italic">Aucun document dans ce lot.</p>
                ) : (
                  <div className="space-y-2">
                    {selectedLot.documents.map((doc) => (
                      <div key={doc.id} className="flex justify-between items-center p-3 border border-gray-100 rounded-lg">
                        <div>
                          <p className="text-sm font-medium text-gray-700">{doc.filename}</p>
                          <p className="text-xs text-gray-400">
                            {doc.provider || "Fournisseur inconnu"} — {doc.total_ttc || "0.00 €"}
                          </p>
                        </div>
                        <button
                          onClick={() => handleRemoveDoc(doc.id)}
                          className="text-xs text-red-500 hover:text-red-700"
                        >
                          Retirer du lot
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                <h3 className="text-lg font-semibold text-gray-800 mb-4">Documents non assignés</h3>
                {unassignedDocs.length === 0 ? (
                  <p className="text-sm text-gray-400 italic">Aucun document disponible à assigner.</p>
                ) : (
                  <div className="space-y-2">
                    {unassignedDocs.map((doc) => (
                      <div key={doc.id} className="flex justify-between items-center p-3 border border-gray-100 rounded-lg">
                        <div>
                          <p className="text-sm font-medium text-gray-700">{doc.filename}</p>
                          <p className="text-xs text-gray-400">
                            {doc.provider || "Fournisseur inconnu"} — {doc.total_ttc || "0.00 €"}
                          </p>
                        </div>
                        <button
                          onClick={() => handleAssignDoc(doc.id)}
                          className="text-xs text-blue-600 hover:text-blue-800 font-medium"
                        >
                          + Ajouter au lot
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

      </main>
    </div>
  );
}

export default LotManagement;