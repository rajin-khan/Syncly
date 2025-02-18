import React from "react";
import Header from "./components/Header";
import PreviewCard from "./components/PreviewCard";
import StorageInfo from "./components/StorageInfo";
import UploadBox from "./components/UploadBox";
import "./styles.css";  // Importing global styles

const App = () => {
  return (
    <div className="app-container">
      <Header />

      <div className="grid-container">
        {[...Array(10)].map((_, i) => (
          <PreviewCard key={i} />
        ))}
      </div>

      <StorageInfo />
      <UploadBox />
    </div>
  );
};

export default App;