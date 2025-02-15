import React from "react";

const PreviewCard = () => (
  <div className="preview-card">
    <div className="preview-header">
      <span className="file-name">FileName.ext</span>
      <button className="download-btn">↓</button>
    </div>
    <div className="preview-body">
      <span>PREVIEW</span>
    </div>
    <div className="preview-footer">IMG</div>
  </div>
);

export default PreviewCard;