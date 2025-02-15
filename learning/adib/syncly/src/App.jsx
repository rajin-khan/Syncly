import React from "react";
import Header from "./components/Header";
import PreviewCard from "./components/PreviewCard";
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
    </div>
  );
};

export default App;