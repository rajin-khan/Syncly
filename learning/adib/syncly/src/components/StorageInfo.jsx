import React from 'react';

const StorageInfo = () => {
  const storageUsed = 47.5;
  const storageTotal = 120;

  return (
    <div className="storage-info">
      <span className="storage-text">
        Storage: {storageUsed} GB of {storageTotal} GB used
      </span>
    </div>
  );
};

export default StorageInfo;