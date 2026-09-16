import { useState } from 'react'
import './App.css'

const apiBaseUrl = import.meta.env.VITE_API_URL ?? '/api'

type Analysis = {
  upload_id: string
  entities_detected: number
  candidate_drawing_clusters: number
  dimensions_detected: number
  detailed_dimensions: number[]
  annotations_detected: number
  selected_primary_cluster: string
  drawing_size: { width: number; height: number }
  bbox: [number, number, number, number]
}

type PdfResult = {
  status: string
  filename: string
}

type UploadResult = {
  upload_id: string
}

const getApiError = async (response: Response, fallback: string) => {
  try {
    const body = (await response.json()) as { detail?: string }
    return body.detail ?? fallback
  } catch {
    return fallback
  }
}

function App() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [pdfResult, setPdfResult] = useState<PdfResult | null>(null)
  const [pdfBlob, setPdfBlob] = useState<Blob | null>(null)
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
    setPdfBlob(null)

    try {
      const formData = new FormData()
      formData.append('file', selectedFile)

      const uploadResponse = await fetch(`${apiBaseUrl}/upload`, {
        method: 'POST',
        body: formData,
      })
      if (!uploadResponse.ok) {
        throw new Error(await getApiError(uploadResponse, 'The file upload failed.'))
      }
      const { upload_id: uploadId } = (await uploadResponse.json()) as UploadResult

      const analysisResponse = await fetch(`${apiBaseUrl}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ upload_id: uploadId }),
      })
      if (!analysisResponse.ok) {
        throw new Error(await getApiError(analysisResponse, 'The backend could not analyze this drawing.'))
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
      const response = await fetch(`${apiBaseUrl}/generate-pdf`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ upload_id: analysis?.upload_id }),
      })
      if (!response.ok) {
        throw new Error('The backend could not generate the PDF.')
      }

      const contentType = response.headers.get('content-type') ?? ''
      if (!contentType.includes('application/pdf')) {
        throw new Error('The backend did not return a PDF file.')
      }

      const filename = response.headers.get('content-disposition')?.match(/filename="?([^";]+)"?/)?.[1]
        ?? 'drawing.pdf'
      setPdfResult({ status: 'pdf_ready', filename })
      setPdfBlob(await response.blob())
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Something went wrong.')
    } finally {
      setIsGenerating(false)
    }
  }

  const getPdfUrl = () => (pdfBlob ? URL.createObjectURL(pdfBlob) : null)

  const handlePreviewPdf = () => {
    const pdfUrl = getPdfUrl()
    if (pdfUrl) {
      window.open(pdfUrl, '_blank', 'noopener,noreferrer')
    }
  }

  const handleDownloadPdf = () => {
    const pdfUrl = getPdfUrl()
    if (!pdfUrl || !pdfResult) return

    const link = document.createElement('a')
    link.href = pdfUrl
    link.download = pdfResult.filename
    link.click()
    URL.revokeObjectURL(pdfUrl)
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
            <div>
              Part dimensions: {analysis.dimensions_detected > 0
                ? `${analysis.detailed_dimensions.length > 0
                  ? analysis.detailed_dimensions.map((value) => value.toFixed(2).replace(/\.?0+$/, '')).join(', ')
                  : `${analysis.dimensions_detected} detected`}`
                : 'None detected'}
            </div>
            <div>Annotations detected: {analysis.annotations_detected}</div>
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
            <button type="button" className="secondary-button" onClick={handlePreviewPdf} disabled={!pdfBlob}>
              Preview
            </button>
            <button type="button" className="secondary-button" onClick={handleDownloadPdf} disabled={!pdfBlob}>
              Download PDF
            </button>
          </div>
        </section>
      )}
    </main>
  )
}

export default App
