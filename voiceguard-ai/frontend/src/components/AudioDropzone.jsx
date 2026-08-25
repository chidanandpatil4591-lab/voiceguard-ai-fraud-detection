import { CheckCircle2, UploadCloud } from 'lucide-react'

/**
 * Audio drop-zone with file-input and drag-and-drop support.
 *
 * Props
 * -----
 * file      : File | null   — currently selected file
 * onChange  : (File) => void
 * disabled  : bool
 */
export default function AudioDropzone({ file, onChange, disabled = false }) {
  function handleDrop(event) {
    event.preventDefault()
    if (disabled) return
    const dropped = event.dataTransfer?.files?.[0]
    if (dropped) onChange(dropped)
  }

  function handleChange(event) {
    const selected = event.target.files?.[0]
    if (selected) onChange(selected)
  }

  return (
    <label
      className={`dropzone ${file ? 'has-file' : ''} ${disabled ? 'disabled' : ''}`}
      onDragOver={(e) => e.preventDefault()}
      onDrop={handleDrop}
    >
      <input
        type="file"
        accept=".wav,.mp3,.m4a,.flac,.ogg,.webm,audio/*"
        onChange={handleChange}
        disabled={disabled}
      />
      {file ? (
        <>
          <CheckCircle2 size={29} />
          <strong>{file.name}</strong>
          <span>{(file.size / 1024 / 1024).toFixed(2)} MB — ready for analysis</span>
        </>
      ) : (
        <>
          <UploadCloud size={29} />
          <strong>Drop a voice recording here</strong>
          <span>WAV · MP3 · M4A · FLAC · OGG · WebM / max 25 MB</span>
          <small>Raw audio is deleted after processing.</small>
        </>
      )}
    </label>
  )
}
