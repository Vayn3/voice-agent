import { createReadStream, existsSync, readdirSync, statSync } from "fs";
import { extname, join } from "path";
import { Readable } from "stream";

export const runtime = "nodejs";

const VIDEO_DIR = join(process.cwd(), "..", "video");
const SUPPORTED_TYPES: Record<string, string> = {
  ".mp4": "video/mp4",
  ".webm": "video/webm",
  ".ogg": "video/ogg",
  ".ogv": "video/ogg",
  ".mov": "video/quicktime",
  ".m4v": "video/mp4"
};

function findFirstVideo() {
  if (!existsSync(VIDEO_DIR)) return null;

  return readdirSync(VIDEO_DIR)
    .filter((name) => SUPPORTED_TYPES[extname(name).toLowerCase()])
    .sort((left, right) => left.localeCompare(right, "zh-CN"))
    .at(0);
}

export async function GET(request: Request) {
  const fileName = findFirstVideo();
  if (!fileName) {
    return new Response("No supported video file found in the project video folder.", {
      status: 404
    });
  }

  const filePath = join(VIDEO_DIR, fileName);
  const fileSize = statSync(filePath).size;
  const contentType = SUPPORTED_TYPES[extname(fileName).toLowerCase()] || "application/octet-stream";
  const range = request.headers.get("range");

  if (range) {
    const match = range.match(/bytes=(\d*)-(\d*)/);
    const start = match?.[1] ? Number(match[1]) : 0;
    const end = match?.[2] ? Number(match[2]) : fileSize - 1;

    if (start >= fileSize || end >= fileSize || start > end) {
      return new Response(null, {
        status: 416,
        headers: {
          "Content-Range": `bytes */${fileSize}`
        }
      });
    }

    const stream = createReadStream(filePath, { start, end });
    return new Response(Readable.toWeb(stream) as ReadableStream, {
      status: 206,
      headers: {
        "Accept-Ranges": "bytes",
        "Content-Length": String(end - start + 1),
        "Content-Range": `bytes ${start}-${end}/${fileSize}`,
        "Content-Type": contentType
      }
    });
  }

  const stream = createReadStream(filePath);
  return new Response(Readable.toWeb(stream) as ReadableStream, {
    headers: {
      "Accept-Ranges": "bytes",
      "Content-Length": String(fileSize),
      "Content-Type": contentType
    }
  });
}
