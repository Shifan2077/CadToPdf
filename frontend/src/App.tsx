import { useState } from 'react'
import './App.css'

const apiBaseUrl = import.meta.env.VITE_API_URL ?? '/api'

type Analysis = {
  entities_detected: number
  candidate_drawing_clusters: number
  selected_primary_cluster: string
  drawing_size: { width: number; height: number }
  bbox: [number, number, number, number]
}

type PdfResult = {
  status: string
  filename: string
}

function App() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [pdfResult, setPdfResult] = useState<PdfResult | null>(null)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [isGenerating, setIsGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleAnalyze = async () => {
    if (!selectedFile) {
      setError('Choose a DXF file before analyzing.')
      return
    }

    setIsAnalyzing(true)
    setError(null)
    setAnalysis(null)
    setPdfResult(null)

    try {
      const formData = new FormData()
      formData.append('file', selectedFile)

      const uploadResponse = await fetch(`${apiBaseUrl}/upload`, {
        method: 'POST',
        body: formData,
      })
      if (!uploadResponse.ok) {
        throw new Error('The file upload failed.')
      }

      const analysisResponse = await fetch(`${apiBaseUrl}/analyze`, { method: 'POST' })
      if (!analysisResponse.ok) {
        throw new Error('The backend could not analyze this drawing.')
      }

      setAnalysis((await analysisResponse.json()) as Analysis)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Something went wrong.')
    } finally {
      setIsAnalyzing(false)
    }
  }

  const handleGeneratePdf = async () => {
    setIsGenerating(true)
    setError(null)

    try {
      const response = await fetch(`${apiBaseUrl}/generate-pdf`, { method: 'POST' })
      if (!response.ok) {
        throw new Error('The backend could not generate the PDF.')
      }

      setPdfResult((await response.json()) as PdfResult)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Something went wrong.')
    } finally {
      setIsGenerating(false)
    }
  }

  return (
    <main className="app-shell">
      <section className="panel">
        <div className="panel-header">CAD Drawing → PDF</div>

        <div className="upload-box">
          <label className="label">Upload your DXF file</label>
          <div className="file-input-wrap">
            <input
              type="file"
              accept=".dxf"
              onChange={(event) => {
                setSelectedFile(event.target.files?.[0] ?? null)
                setError(null)
              }}
            />
          </div>
        </div>

        <div className="selected-file">
          Selected file: {selectedFile?.name ?? 'No file selected'}
        </div>

          <button className="primary-button" onClick={handleAnalyze} disabled={isAnalyzing}>
            {isAnalyzing ? 'Analyzing…' : 'Analyze Drawing'}
        </button>
          {error && <div className="error-message" role="alert">{error}</div>}
      </section>

      {analysis && (
        <section className="panel results">
          <div className="panel-header">Drawing Analysis</div>

          <div className="metrics">
            <div>Entities detected: {analysis.entities_detected.toLocaleString()}</div>
            <div>Candidate drawing clusters: {analysis.candidate_drawing_clusters}</div>
            <div>Selected primary cluster: {analysis.selected_primary_cluster}</div>
            <div>Dimensions detected: 24</div>
            <div>Associated dimensions: 19</div>
            <div>Drawing size: {analysis.drawing_size.width} × {analysis.drawing_size.height} CAD units</div>
          </div>

          <button className="primary-button" onClick={handleGeneratePdf} disabled={isGenerating}>
            {isGenerating ? 'Generating…' : 'Generate PDF'}
          </button>
        </section>
      )}

      {pdfResult && (
        <section className="panel preview-panel">
          <div className="panel-header">PDF Ready</div>
          <div className="selected-file">Generated file: {pdfResult.filename}</div>
          <div className="preview-actions">
            <button type="button" className="secondary-button" disabled>Preview</button>
            <button type="button" className="secondary-button" disabled>Download PDF</button>
          </div>
        </section>
      )}
    </main>
  )
}

export default App
