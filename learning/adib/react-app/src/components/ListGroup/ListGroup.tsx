import { useState } from "react";
import styles from "./ListGroup.css";
import styled from "styled-components";

const List = styled.ul`
  list-style: none;
  padding: 0;
`;

interface ListItemProps {
    active: boolean;
}

const ListItem = styled.li<ListItemProps>`
    padding: 5px 0;
    background: ${props => props.active ? 'blue' : 'null'}
`
interface Props {
  items: string[];
  heading: string;
  onSelectItem: (item: string) => void;
}

function ListGroup({ items, heading, onSelectItem }: Props) {
  //Hook
  const [selectedIndex, setSelectedIndex] = useState(0);

  //below, we learn how true && 1 = 1, or true && 'rajin' = 'rajin', and false && 'rajin' = false
  //this is often used in conditional rendering.
  return (
    <>
      <h1>{heading}</h1>
      {items.length === 0 && <p>No item found</p>}
      <List className="list-group">
        {items.map((item, index) => (
          <ListItem
          active={index===selectedIndex}
            key={item}
            onClick={() => {
              setSelectedIndex(index);
              onSelectItem(item);
            }}
          >
            {item}
          </ListItem>
        ))}
      </List>
    </>
  );
}

export default ListGroup;
