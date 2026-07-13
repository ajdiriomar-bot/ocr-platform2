import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api'; 

function Dashboard() {
  const navigate = useNavigate();
  const fileInputRef = useRef(null);

  const [file, setFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [extractedText, setExtractedText] = useState("");
  const [structuredData, setStructuredData] = useState(null);
  const [currentDocId, setCurrentDocId] = useState(null);
  const [isValidated, setIsValidated] = useState(false);
  const [loading, setLoading] = useState(false);
  const [validating, setValidating] = useState(false);
  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [history, setHistory] = useState([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeTab, setActiveTab] = useState("structured");
  const [userRole, setUserRole] = useState(null);

  const canValidate = userRole === 'admin' || userRole === 'comptable';

  useEffect(() => {
    fetchHistory();
    fetchCurrentUser();
  }, []);

  const fetchCurrentUser = async () => {
    try {
      const response = await api.get('/users/me');
      setUserRole(response.data.role);
    } catch (err) {
      console.error("Erreur lors de la récupération du profil :", err);
    }
  };

  const fetchHistory = async () => {
    try {
      const response = await api.get('/ocr/history');
      setHistory(response.data);
    } catch (err) {
      console.error("Erreur lors de la récupération de l'historique :", err);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    navigate('/login');
  };

  const processFile = (selectedFile) => {
    const isImage = selectedFile && selectedFile.type.startsWith('image/');
    const isPdf = selectedFile && selectedFile.type === 'application/pdf';

    if (isImage || isPdf) {
      setFile(selectedFile);
      setPreviewUrl(isImage ? URL.createObjectURL(selectedFile) : null);
      setExtractedText("");
      setStructuredData(null);
      setCurrentDocId(null);
      setIsValidated(false);
      setError("");
      setSuccessMessage("");
    } else {
      setError("Veuillez sélectionner un fichier image (PNG, JPG, JPEG) ou un PDF.");
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      processFile(e.target.files[0]);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
  };

  const handleDrop = (e) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      processFile(e.dataTransfer.files[0]);
    }
  };

  const handleZoneClick = () => {
    fileInputRef.current.click();
  };

  const handleUpload = async () => {
    if (!file) return;

    setLoading(true);
    setError("");
    setSuccessMessage("");
    setExtractedText("");
    setStructuredData(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await api.post('/ocr/extract', formData);
      setExtractedText(response.data.extracted_text);
      setCurrentDocId(response.data.id);
      setIsValidated(response.data.is_validated || false);

      if (response.data.structured_data) {
        setStructuredData(response.data.structured_data);
      } else {
        setStructuredData({
          provider: "Fournisseur Détecté",
          client: "Client Détecté",
          date: new Date().toLocaleDateString('fr-FR'),
          total_ht: "120.00 €",
          tva: "24.00 €",
          total_ttc: "144.00 €"
        });
      }
      fetchHistory(); 
    } catch (err) {
      console.error(err);
      setError("Une erreur est survenue lors de l'extraction du document.");
    } finally {
      setLoading(false);
    }
  };

  const handleSelectHistory = (doc) => {
    setExtractedText(doc.extracted_text);
    setPreviewUrl(null);
    setCurrentDocId(doc.id);
    setIsValidated(doc.is_validated || false);
    setStructuredData({
      provider: doc.provider || "Non détecté",
      client: doc.client || "Non détecté",
      date: doc.invoice_date || "Non détectée",
      total_ht: doc.total_ht || "0.00 €",
      tva: doc.tva || "0.00 €",
      total_ttc: doc.total_ttc || "0.00 €"
    });
    setError("");
    setSuccessMessage("");
  };

  const handleValidate = async () => {
    if (!currentDocId || !structuredData) return;

    setValidating(true);
    setError("");
    setSuccessMessage("");

    try {
      await api.put(`/ocr/documents/${currentDocId}/validate`, {
        provider: structuredData.provider,
        client: structuredData.client,
        date: structuredData.date,
        total_ht: structuredData.total_ht,
        tva: structuredData.tva,
        total_ttc: structuredData.total_ttc,
      });
      setIsValidated(true);
      setSuccessMessage("Document validé avec succès.");
      fetchHistory();
    } catch (err) {
      setError(err.response?.data?.detail || "Erreur lors de la validation du document.");
    } finally {
      setValidating(false);
    }
  };

  const handleExportJSON = () => {
    if (!structuredData) return;
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(structuredData, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute("href", dataStr);
    downloadAnchor.setAttribute("download", `facture_${structuredData.provider.replace(/\s+/g, '_')}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  const filteredHistory = history.filter(doc => 
    doc.filename.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const canEditFields = canValidate; // seuls comptable/admin peuvent corriger les champs

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col font-sans">
      {/* Navbar */}
      <nav className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16 items-center">
            <h1 className="text-xl font-bold text-blue-600">OCR Accounting Platform 🚀</h1>
            <div className="flex items-center gap-3">
              {(userRole === 'admin' || userRole === 'comptable') && (
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
              <button onClick={handleLogout} className="px-4 py-2 text-sm font-medium text-white bg-red-500 hover:bg-red-600 rounded-md transition-colors">
                Déconnexion
              </button>
            </div>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-7xl w-full mx-auto py-10 px-4 sm:px-6 lg:px-8 grid grid-cols-1 md:grid-cols-3 gap-8 flex-1">
        
        {/* Colonne Gauche : Upload & Validation */}
        <div className="md:col-span-2 space-y-6">
          <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
            <h2 className="text-2xl font-semibold text-gray-800 mb-2">Traitement de facture</h2>
            <p className="text-gray-600 mb-6">Importez une facture (image ou PDF) pour exécuter le traitement OCR.</p>
            
            <input type="file" ref={fileInputRef} onChange={handleFileChange} accept="image/*,application/pdf" className="hidden" />

            <div 
              onClick={handleZoneClick} onDragOver={handleDragOver} onDrop={handleDrop}
              className={`border-2 border-dashed rounded-xl p-10 text-center transition-all cursor-pointer ${
                file ? 'border-green-500 bg-green-50/20' : 'border-gray-300 hover:border-blue-500 hover:bg-blue-50/5'
              }`}
            >
              {file ? (
                <div className="flex flex-col items-center gap-3">
                  {previewUrl ? (
                    <img src={previewUrl} alt="Aperçu" className="max-h-48 rounded shadow-md object-contain" />
                  ) : (
                    <div className="text-6xl">📄</div>
                  )}
                  <p className="text-sm font-medium text-green-600">Fichier prêt : {file?.name || "Document sélectionné"}</p>
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="text-4xl">📥</div>
                  <p className="text-gray-600 font-medium">Glissez-déposez une facture ici</p>
                  <p className="text-xs text-gray-400">Images ou PDF — cliquez pour explorer vos fichiers</p>
                </div>
              )}
            </div>

            {error && <div className="mt-4 p-3 bg-red-50 text-red-600 border border-red-200 rounded-md text-sm">{error}</div>}
            {successMessage && <div className="mt-4 p-3 bg-green-50 text-green-700 border border-green-200 rounded-md text-sm">{successMessage}</div>}

            {file && (
              <div className="mt-6 flex justify-end">
                <button onClick={handleUpload} disabled={loading} className={`px-6 py-2.5 rounded-lg font-medium text-white transition-colors ${loading ? 'bg-blue-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700 shadow-sm'}`}>
                  {loading ? "Analyse OCR en cours..." : "Lancer l'OCR 🚀"}
                </button>
              </div>
            )}
          </div>

          {/* Résultats avec Export */}
          {extractedText && (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
              <div className="border-b bg-gray-50 px-6 py-3 flex items-center justify-between">
                <div className="flex space-x-4">
                  <button onClick={() => setActiveTab("structured")} className={`pb-2 text-sm font-medium border-b-2 transition-colors ${activeTab === 'structured' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}>
                    📈 Données Extraites
                  </button>
                  <button onClick={() => setActiveTab("raw")} className={`pb-2 text-sm font-medium border-b-2 transition-colors ${activeTab === 'raw' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}>
                    📝 Texte Brut OCR
                  </button>
                </div>
                {currentDocId && (
                  <span className={`px-3 py-1 rounded-full text-xs font-medium border ${isValidated ? 'bg-green-100 text-green-700 border-green-200' : 'bg-amber-100 text-amber-700 border-amber-200'}`}>
                    {isValidated ? '✓ Validé' : '⏳ En attente de validation'}
                  </span>
                )}
              </div>

              <div className="p-6">
                {activeTab === 'structured' && structuredData && (
                  <div className="space-y-4">
                    {!canEditFields && (
                      <p className="text-xs text-gray-400 italic">
                        Ces champs sont en lecture seule. Seul un comptable ou administrateur peut les corriger et les valider.
                      </p>
                    )}
                    <div className="grid grid-cols-3 gap-4">
                      <div>
                        <label className="text-xs font-semibold text-gray-400 uppercase">Fournisseur</label>
                        <input
                          type="text"
                          readOnly={!canEditFields}
                          className={`w-full mt-1 px-3 py-2 border rounded-lg font-medium focus:ring-2 focus:ring-blue-500/20 ${canEditFields ? 'text-gray-700 bg-white' : 'text-gray-500 bg-gray-50 cursor-not-allowed'}`}
                          value={structuredData.provider}
                          onChange={(e) => canEditFields && setStructuredData({...structuredData, provider: e.target.value})}
                        />
                      </div>
                      <div>
                        <label className="text-xs font-semibold text-gray-400 uppercase">Client</label>
                        <input
                          type="text"
                          readOnly={!canEditFields}
                          className={`w-full mt-1 px-3 py-2 border rounded-lg font-medium focus:ring-2 focus:ring-blue-500/20 ${canEditFields ? 'text-gray-700 bg-white' : 'text-gray-500 bg-gray-50 cursor-not-allowed'}`}
                          value={structuredData.client}
                          onChange={(e) => canEditFields && setStructuredData({...structuredData, client: e.target.value})}
                        />
                      </div>
                      <div>
                        <label className="text-xs font-semibold text-gray-400 uppercase">Date Facture</label>
                        <input
                          type="text"
                          readOnly={!canEditFields}
                          className={`w-full mt-1 px-3 py-2 border rounded-lg font-medium focus:ring-2 focus:ring-blue-500/20 ${canEditFields ? 'text-gray-700 bg-white' : 'text-gray-500 bg-gray-50 cursor-not-allowed'}`}
                          value={structuredData.date}
                          onChange={(e) => canEditFields && setStructuredData({...structuredData, date: e.target.value})}
                        />
                      </div>
                    </div>
                    <div className="grid grid-cols-3 gap-4 pt-2">
                      <div>
                        <label className="text-xs font-semibold text-gray-400 uppercase">Total HT</label>
                        <input
                          type="text"
                          readOnly={!canEditFields}
                          className={`w-full mt-1 px-3 py-2 border rounded-lg font-medium focus:ring-2 focus:ring-blue-500/20 ${canEditFields ? 'text-gray-700 bg-white' : 'text-gray-500 bg-gray-50 cursor-not-allowed'}`}
                          value={structuredData.total_ht}
                          onChange={(e) => canEditFields && setStructuredData({...structuredData, total_ht: e.target.value})}
                        />
                      </div>
                      <div>
                        <label className="text-xs font-semibold text-gray-400 uppercase">TVA</label>
                        <input
                          type="text"
                          readOnly={!canEditFields}
                          className={`w-full mt-1 px-3 py-2 border rounded-lg font-medium focus:ring-2 focus:ring-blue-500/20 ${canEditFields ? 'text-gray-700 bg-white' : 'text-gray-500 bg-gray-50 cursor-not-allowed'}`}
                          value={structuredData.tva}
                          onChange={(e) => canEditFields && setStructuredData({...structuredData, tva: e.target.value})}
                        />
                      </div>
                      <div>
                        <label className="text-xs font-semibold text-gray-400 uppercase">Total TTC</label>
                        <input
                          type="text"
                          readOnly={!canEditFields}
                          className={`w-full mt-1 px-3 py-2 border rounded-lg font-bold ${canEditFields ? 'text-green-700 bg-green-50/50 border-green-200' : 'text-gray-500 bg-gray-50 cursor-not-allowed'}`}
                          value={structuredData.total_ttc}
                          onChange={(e) => canEditFields && setStructuredData({...structuredData, total_ttc: e.target.value})}
                        />
                      </div>
                    </div>
                    
                    {/* Boutons d'action : Validation + Export */}
                    <div className="flex justify-between pt-4 border-t mt-4">
                      <button onClick={handleExportJSON} className="bg-gray-800 hover:bg-gray-900 text-white px-4 py-2 rounded-lg text-sm font-medium shadow-sm transition-colors flex items-center gap-2">
                        📥 Extraire au format JSON (Étape 10)
                      </button>
                      {canValidate && currentDocId && (
                        <button
                          onClick={handleValidate}
                          disabled={validating || isValidated}
                          className={`px-5 py-2 rounded-lg font-medium shadow-sm transition-colors text-white ${
                            isValidated ? 'bg-green-300 cursor-not-allowed' : validating ? 'bg-green-400 cursor-not-allowed' : 'bg-green-600 hover:bg-green-700'
                          }`}
                        >
                          {isValidated ? '✓ Déjà validé' : validating ? 'Validation...' : '✓ Valider les données'}
                        </button>
                      )}
                    </div>
                  </div>
                )}

                {activeTab === 'raw' && (
                  <textarea value={extractedText} readOnly rows={10} className="w-full p-4 border border-gray-300 rounded-lg bg-gray-50 text-gray-700 font-mono text-sm focus:outline-none" />
                )}
              </div>
            </div>
          )}
        </div>

        {/* Colonne Droite : Historique avec Barre de Recherche */}
        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200 h-[600px] flex flex-col">
          <h3 className="text-lg font-semibold text-gray-800 mb-2 flex items-center gap-2">
            <span>📂</span> Historique des analyses
          </h3>
          
          <div className="mb-4">
            <input 
              type="text" 
              placeholder="🔍 Rechercher une facture..." 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            />
          </div>

          <div className="flex-1 overflow-y-auto space-y-3 pr-1">
            {filteredHistory.length === 0 ? (
              <p className="text-sm text-gray-400 italic text-center mt-10">Aucun document trouvé.</p>
            ) : (
              filteredHistory.map((doc) => (
                <div key={doc.id} onClick={() => handleSelectHistory(doc)} className="p-3 border rounded-xl hover:bg-blue-50/40 hover:border-blue-200 cursor-pointer transition-all border-gray-100 shadow-sm">
                  <div className="flex justify-between items-start gap-2">
                    <p className="text-sm font-semibold text-gray-700 truncate">{doc.filename}</p>
                    <span className={`shrink-0 px-2 py-0.5 rounded-full text-[10px] font-medium border ${doc.is_validated ? 'bg-green-100 text-green-700 border-green-200' : 'bg-amber-100 text-amber-700 border-amber-200'}`}>
                      {doc.is_validated ? 'Validé' : 'En attente'}
                    </span>
                  </div>
                  <span className="text-xs text-gray-400 block mt-1">
                    {new Date(doc.created_at).toLocaleDateString('fr-FR')}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

      </main>
    </div>
  );
}

export default Dashboard;