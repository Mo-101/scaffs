import JSZip from 'jszip';
import { ProjectFile } from '../types/scaffold';

export async function downloadProjectZip(projectName: string, files: ProjectFile[]): Promise<void> {
  const zip = new JSZip();

  // Add each file to the zip archive
  for (const file of files) {
    // Normalise file path (remove leading slash if present)
    const cleanPath = file.path.startsWith('/') ? file.path.substring(1) : file.path;
    zip.file(cleanPath, file.content);
  }

  // Generate zip blob
  const content = await zip.generateAsync({
    type: 'blob',
    compression: 'DEFLATE',
    compressionOptions: {
      level: 6,
    },
  });

  // Create download link and trigger
  const fileName = `${projectName || 'node22-scaffold'}.zip`;
  const url = URL.createObjectURL(content);
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
