import React from "react";
import { Plus, Search } from "lucide-react";

const Header = () => {
  return (
    <header className="header">
      <button className="add-storage">
        <Plus size={14} /> <span>ADD MORE STORAGE</span>
      </button>
      <div className="logo">syncly<span className="cloud-icon">☁</span></div>
      <Search size={18} className="search-icon" />
    </header>
  );
};

export default Header;