import React from "react";
import Header from "./components/Header";
import PreviewCard from "./components/PreviewCard";
import UploadBox from "./components/UploadBox";
import "./styles.css";

const App = () => {
  return (
    <div className="app-container">
      <Header />
      <div className="grid-container">
        {[...Array(10)].map((_, i) => (
          <PreviewCard key={i} />
        ))}
      </div>
      <UploadBox />
    </div>
  );
};

export default App;