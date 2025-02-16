import React from "react";
import { Plus } from "lucide-react";

const UploadBox = () => {
  return (
    <div className="upload-box">
      <span>drag items here</span>
      <Plus size={14} />
      <span>or click to upload</span>
    </div>
  );
};

export default UploadBox;